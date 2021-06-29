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

from unittest import mock

from oslo_utils import uuidutils

from delfin import context
from delfin import db
from delfin import test
from delfin.common import constants
from delfin.db.sqlalchemy.models import Task
from delfin.task_manager.scheduler.schedulers.telemetry.telemetry_job import \
    TelemetryJob

fake_telemetry_job = {
    Task.id.name: 2,
    Task.storage_id.name: uuidutils.generate_uuid(),
    Task.args.name: {},
    Task.interval.name: 10,
    Task.method.name: constants.TelemetryCollection.PERFORMANCE_TASK_METHOD,
    Task.last_run_time.name: None,
}

fake_telemetry_jobs = [
    fake_telemetry_job,
]

fake_telemetry_job_deleted = {
    Task.id.name: 2,
    Task.storage_id.name: uuidutils.generate_uuid(),
    Task.args.name: {},
    Task.interval.name: 10,
    Task.method.name: constants.TelemetryCollection.PERFORMANCE_TASK_METHOD,
    Task.last_run_time.name: None,
    Task.deleted.name: True,
}

fake_telemetry_jobs_deleted = [
    fake_telemetry_job_deleted,
]
# With method name as None
Incorrect_telemetry_job = {
    Task.id.name: 2,
    Task.storage_id.name: uuidutils.generate_uuid(),
    Task.args.name: {},
    Task.interval.name: 10,
    Task.method.name: None,
    Task.last_run_time.name: None,
}

Incorrect_telemetry_jobs = [
    Incorrect_telemetry_job,
]


class TestTelemetryJob(test.TestCase):

    @mock.patch.object(db, 'task_get_all',
                       mock.Mock(return_value=fake_telemetry_jobs))
    @mock.patch.object(db, 'task_update',
                       mock.Mock(return_value=fake_telemetry_job))
    @mock.patch.object(db, 'task_get',
                       mock.Mock(return_value=fake_telemetry_job))
    @mock.patch(
        'apscheduler.schedulers.background.BackgroundScheduler.add_job')
    def test_telemetry_job_scheduling(self, mock_add_job):
        ctx = context.get_admin_context()
        telemetry_job = TelemetryJob(ctx)
        # call telemetry job scheduling
        telemetry_job()
        self.assertEqual(mock_add_job.call_count, 1)

    @mock.patch.object(db, 'task_get_all',
                       mock.Mock(return_value=Incorrect_telemetry_jobs))
    @mock.patch.object(db, 'task_update',
                       mock.Mock(return_value=Incorrect_telemetry_job))
    @mock.patch.object(db, 'task_get',
                       mock.Mock(return_value=Incorrect_telemetry_job))
    @mock.patch(
        'apscheduler.schedulers.background.BackgroundScheduler.add_job',
        mock.Mock())
    @mock.patch('logging.LoggerAdapter.error')
    def test_telemetry_job_scheduling_exception(self, mock_log_error):
        ctx = context.get_admin_context()
        telemetry_job = TelemetryJob(ctx)
        # call telemetry job scheduling
        telemetry_job()
        self.assertEqual(mock_log_error.call_count, 2)

    @mock.patch.object(db, 'task_delete',
                       mock.Mock())
    @mock.patch.object(db, 'task_get_all',
                       mock.Mock(return_value=fake_telemetry_jobs_deleted))
    @mock.patch.object(db, 'task_update',
                       mock.Mock(return_value=fake_telemetry_job))
    @mock.patch.object(db, 'task_get',
                       mock.Mock(return_value=fake_telemetry_job))
    @mock.patch(
        'apscheduler.schedulers.background.BackgroundScheduler.add_job',
        mock.Mock())
    @mock.patch('logging.LoggerAdapter.error')
    def test_telemetry_removal_success(self, mock_log_error):
        ctx = context.get_admin_context()
        telemetry_job = TelemetryJob(ctx)
        # call telemetry job scheduling
        telemetry_job()
        self.assertEqual(mock_log_error.call_count, 1)
