# Copyright 2021 The SODA Authors.
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

import six
from eventlet import event
from oslo_log import log
from oslo_utils import importutils
from oslo_utils import uuidutils

from delfin import context
from delfin import utils
# from apscheduler.schedulers.background import BackgroundScheduler
from delfin.task_manager.scheduler.fixed_interval_looping_scheduler import \
    FixedIntervalLoopingScheduler
from delfin.task_manager.scheduler.schedulers.telemetry.failed_telemetry_job \
    import FailedTelemetryJob
from delfin.task_manager.scheduler.schedulers.telemetry.telemetry_job import \
    TelemetryJob

LOG = log.getLogger(__name__)

SCHEDULER_BOOT_JOBS = [
    TelemetryJob.__module__ + '.' + TelemetryJob.__name__,
    FailedTelemetryJob.__module__ + '.' + FailedTelemetryJob.__name__
]


@six.add_metaclass(utils.Singleton)
class SchedulerManager(object):
    def __init__(self, scheduler=None):
        if not scheduler:
            # scheduler = BackgroundScheduler()
            scheduler = FixedIntervalLoopingScheduler()
        self.scheduler = scheduler

        self.boot_jobs_scheduled = False
        self.ctx = context.get_admin_context()

    def start(self):
        """ Initialise the schedulers for periodic job creation
        """
        if not self.scheduler.running:
            LOG.info("Starting job scheduler")
            self.scheduler.start()

        if not self.boot_jobs_scheduled:
            try:
                for job in SCHEDULER_BOOT_JOBS:
                    job_class = importutils.import_class(job)
                    job_instance = job_class(self.ctx)

                    # Create a jobs for periodic scheduling
                    job_id = uuidutils.generate_uuid()
                    self.scheduler.add_job(job_instance,
                                           interval=job_class.job_interval(),
                                           job_id=job_id)
                    LOG.info("[%s] boot job scheduled" % job)

            except Exception as e:
                # TODO: Currently failure of scheduler is failing task manager
                #  start flow, it is logged and ignored.
                LOG.error("Failed to initialize periodic tasks, reason: %s.",
                          six.text_type(e))
                raise e

    def stop(self):
        """Cleanup periodic jobs"""
        LOG.info("Shutting down scheduler")
        self.scheduler.shutdown()

    def get_scheduler(self):
        return self.scheduler
