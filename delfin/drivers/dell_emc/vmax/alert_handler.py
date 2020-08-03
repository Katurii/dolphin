# Copyright 2020 The SODA Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime

from oslo_log import log

from delfin import exception
from delfin.common import constants
from delfin.drivers.dell_emc.vmax import alert_mapper

LOG = log.getLogger(__name__)


class AlertHandler(object):
    """Alert handling functions for vmax driver"""

    # Translation of trap severity to alert model severity
    SEVERITY_MAP = {"emergency": constants.Severity.FATAL,
                    "alert": constants.Severity.CRITICAL,
                    "critical": constants.Severity.CRITICAL,
                    "error": constants.Severity.MAJOR,
                    "warning": constants.Severity.WARNING,
                    "notify": constants.Severity.WARNING,
                    "info": constants.Severity.INFORMATIONAL,
                    "debug": constants.Severity.INFORMATIONAL,
                    "mark": constants.Severity.INFORMATIONAL}

    # Translation of trap resource type to alert model resource type
    RESOURCE_TYPE_MAP = {
        "hub": constants.ResourceType.NETWORK,
        "switch": constants.ResourceType.NETWORK,
        "gateway": constants.ResourceType.NETWORK,
        "converter": constants.ResourceType.NETWORK,
        "hba": constants.ResourceType.NETWORK,
        "proxy-agent": constants.ResourceType.NETWORK,
        "storage-device": constants.ResourceType.STORAGE,
        "host": constants.ResourceType.SERVER,
        "storage-subsystem": constants.ResourceType.STORAGE,
        "module": constants.ResourceType.OTHER,
        "swdriver": constants.ResourceType.OTHER,
        "storage-access-device": constants.ResourceType.STORAGE,
        "wdm": constants.ResourceType.OTHER,
        "ups": constants.ResourceType.OTHER,
        "other": constants.ResourceType.OTHER}

    # Attributes mandatory in alert info to proceed with model filling
    _mandatory_alert_attributes = ('emcAsyncEventCode',
                                   'connUnitEventSeverity',
                                   'connUnitEventType', 'connUnitEventDescr',
                                   'connUnitType',
                                   'emcAsyncEventComponentType',
                                   'emcAsyncEventComponentName',
                                   'emcAsyncEventSource')

    def __init__(self):
        pass

    def parse_alert(self, context, alert):
        """Parse alert data got from alert manager and fill the alert model."""

        # Check for mandatory alert attributes
        for attr in self._mandatory_alert_attributes:
            if not alert.get(attr):
                msg = "Mandatory information %s missing in alert message. " \
                      % attr
                raise exception.InvalidInput(msg)

        alert_model = {}

        # Fill alarm id and fill alarm_name with corresponding mapping names
        alert_model['alert_id'] = alert['emcAsyncEventCode']
        alert_model['alert_name'] = alert_mapper.alarm_id_name_mapping.get(
            alert_model['alert_id'], alert_model['alert_id'])

        alert_model['severity'] = self.SEVERITY_MAP.get(
            alert['connUnitEventSeverity'],
            constants.Severity.INFORMATIONAL)

        alert_model['category'] = constants.Category.NOT_SPECIFIED
        alert_model['type'] = alert['connUnitEventType']

        alert_model['sequence_number'] = alert['connUnitEventId']

        # trap info do not contain occur time, update with received time
        # Get date and time. Format will be like : Wed May 20 01:53:29 2020
        curr_time = datetime.now()
        alert_model['occur_time'] = curr_time.strftime('%c')
        alert_model['detailed_info'] = alert['connUnitEventDescr']
        alert_model['recovery_advice'] = 'None'
        alert_model['resource_type'] = self.RESOURCE_TYPE_MAP.get(
            alert['connUnitType'], constants.ResourceType.OTHER)

        # Location is name-value pair having component type and component name
        component_type = alert_mapper.component_type_mapping.get(
            alert.get('emcAsyncEventComponentType'), "")
        alert_model['location'] = 'Array id=' \
                                  + alert['connUnitName'] \
                                  + ',Component type=' \
                                  + component_type \
                                  + ',Component name=' \
                                  + alert['emcAsyncEventComponentName'] \
                                  + ',Event source=' \
                                  + alert['emcAsyncEventSource']

        return alert_model

    def add_trap_config(self, context, storage_id, trap_config):
        """Config the trap receiver in storage system."""
        pass

    def remove_trap_config(self, context, storage_id, trap_config):
        """Remove trap receiver configuration from storage system."""
        pass

    def clear_alert(self, context, storage_id, alert):
        """Clear alert from storage system."""
        pass
