# Copyright 2020 The SODA Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy

from oslo_config import cfg
from oslo_log import log
from oslo_utils import timeutils

from delfin import coordination, context
from delfin import db
from delfin import exception
from delfin.api import api_utils
from delfin.api import validation
from delfin.api.common import wsgi
from delfin.api.schemas import storages as schema_storages
from delfin.api.views import storages as storage_view
from delfin.common import constants
from delfin.drivers import api as driverapi
from delfin.i18n import _
from delfin.task_manager import rpcapi as task_rpcapi
from delfin.task_manager.tasks import resources

LOG = log.getLogger(__name__)
CONF = cfg.CONF


class StorageController(wsgi.Controller):
    def __init__(self):
        super().__init__()
        self.task_rpcapi = task_rpcapi.TaskAPI()
        self.driver_api = driverapi.API()
        self.search_options = ['name', 'vendor', 'model', 'status',
                               'serial_number']

    def _get_storages_search_options(self):
        """Return storages search options allowed ."""
        return self.search_options

    def index(self, req):
        ctxt = req.environ['delfin.context']
        query_params = {}
        query_params.update(req.GET)
        # update options  other than filters
        sort_keys, sort_dirs = api_utils.get_sort_params(query_params)
        marker, limit, offset = api_utils.get_pagination_params(query_params)
        # strip out options except supported search  options
        api_utils.remove_invalid_options(ctxt, query_params,
                                         self._get_storages_search_options())

        storages = db.storage_get_all(ctxt, marker, limit, sort_keys,
                                      sort_dirs, query_params, offset)
        return storage_view.build_storages(storages)

    def show(self, req, id):
        ctxt = req.environ['delfin.context']
        storage = db.storage_get(ctxt, id)
        return storage_view.build_storage(storage)

    @wsgi.response(201)
    @validation.schema(schema_storages.create)
    def create(self, req, body):
        """Register a new storage device."""
        ctxt = req.environ['delfin.context']
        access_info_dict = body

        # Lock to avoid synchronous creating.
        for access in constants.ACCESS_TYPE:
            if access_info_dict.get(access) is not None:
                host = access_info_dict.get('rest').get('host')
                port = access_info_dict.get('rest').get('port')
                break
        lock_name = 'storage-create-' + host + '-' + str(port)
        coordination.synchronized(lock_name)

        if self._storage_exist(ctxt, access_info_dict):
            raise exception.StorageAlreadyExists()

        storage = self.driver_api.discover_storage(ctxt,
                                                   access_info_dict)

        # Registration success, sync resource collection for this storage
        try:
            self.sync(req, storage['id'])

            # Post registration, trigger alert sync
            self.task_rpcapi.sync_storage_alerts(ctxt, storage['id'],
                                                 query_para=None)
        except Exception as e:
            # Unexpected error occurred, while syncing resources.
            msg = _('Failed to sync resources for storage: %(storage)s. '
                    'Error: %(err)s') % {'storage': storage['id'], 'err': e}
            LOG.error(msg)
        return storage_view.build_storage(storage)

    @wsgi.response(202)
    def delete(self, req, id):
        ctxt = req.environ['delfin.context']
        storage = db.storage_get(ctxt, id)

        for subclass in resources.StorageResourceTask.__subclasses__():
            self.task_rpcapi.remove_storage_resource(
                ctxt,
                storage['id'],
                subclass.__module__ + '.' + subclass.__name__)
        self.task_rpcapi.remove_storage_in_cache(ctxt, storage['id'])

    @wsgi.response(202)
    def sync_all(self, req):
        """
        :param req:
        :return: it's a Asynchronous call. so return 202 on success. sync_all
        api performs the storage device info, storage_pool,
         volume etc. tasks on each registered storage device.
        """
        ctxt = req.environ['delfin.context']

        storages = db.storage_get_all(ctxt)
        LOG.debug("Total {0} registered storages found in database".
                  format(len(storages)))
        resource_count = len(resources.StorageResourceTask.__subclasses__())

        for storage in storages:
            try:
                _set_synced_if_ok(ctxt, storage['id'], resource_count)
            except exception.InvalidInput as e:
                LOG.warn('Can not start new sync task for %s, reason is %s'
                         % (storage['id'], e.msg))
                continue
            else:
                for subclass in resources.StorageResourceTask.__subclasses__():
                    self.task_rpcapi.sync_storage_resource(
                        ctxt,
                        storage['id'],
                        subclass.__module__ + '.' + subclass.__name__)

    @wsgi.response(202)
    def sync(self, req, id):
        """
        :param req:
        :param id:
        :return:
        """
        ctxt = req.environ['delfin.context']
        storage = db.storage_get(ctxt, id)
        resource_count = len(resources.StorageResourceTask.__subclasses__())
        _set_synced_if_ok(ctxt, storage['id'], resource_count)
        for subclass in resources.StorageResourceTask.__subclasses__():
            self.task_rpcapi.sync_storage_resource(
                ctxt,
                storage['id'],
                subclass.__module__ + '.' + subclass.__name__)

    def perf_collect(self, storage_id, interval, is_history, resource):
        ctxt = context.RequestContext()

        LOG.debug("Request received to create task for storage_id:{0} and"
                  " resource_type:{1}".format(storage_id, resource))

        self.task_rpcapi.performance_metrics_collection(
            ctxt, storage_id, interval, is_history,
            resources.PerformanceCollectionTask.__module__ +
            '.' + constants.PERF_POLLING_TYPE.get(resource))

    def _storage_exist(self, context, access_info):
        access_info_dict = copy.deepcopy(access_info)

        # Remove unrelated query fields
        unrelated_fields = ['username', 'password']
        for access in constants.ACCESS_TYPE:
            if access_info_dict.get(access):
                for key in unrelated_fields:
                    access_info_dict[access].pop(key)

        # Check if storage is registered
        access_info_list = db.access_info_get_all(context,
                                                  filters=access_info_dict)
        for _access_info in access_info_list:
            try:
                storage = db.storage_get(context, _access_info['storage_id'])
                if storage:
                    LOG.error("Storage %s has same access "
                              "information." % storage['id'])
                    return True
            except exception.StorageNotFound:
                # Suppose storage was not saved successfully after access
                # information was saved in database when registering storage.
                # Therefore, removing access info if storage doesn't exist to
                # ensure the database has no residual data.
                LOG.debug("Remove residual access information.")
                db.access_info_delete(context, _access_info['storage_id'])

        return False


def create_resource():
    return wsgi.Resource(StorageController())


@coordination.synchronized('{storage_id}')
def _set_synced_if_ok(context, storage_id, resource_count):
    try:
        storage = db.storage_get(context, storage_id)
    except exception.StorageNotFound:
        msg = 'Storage %s not found when try to set sync_status' \
              % storage_id
        raise exception.InvalidInput(message=msg)
    else:
        last_update = storage['updated_at'] or storage['created_at']
        current_time = timeutils.utcnow()
        interval = (current_time - last_update).seconds
        # If last synchronization was within
        # CONF.sync_task_expiration(in seconds), and the sync status
        # is not SYNCED, it means some sync task is still running,
        # the new sync task should not launch
        if interval < CONF.sync_task_expiration and \
                storage['sync_status'] != constants.SyncStatus.SYNCED:
            msg = 'Sync task is running for %s' % storage['id']
            raise exception.InvalidInput(message=msg)
        storage['sync_status'] = resource_count
        db.storage_update(context, storage['id'], storage)
