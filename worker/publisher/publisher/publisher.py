#   Copyright 2014-2016 PUNCH Cyber Analytics Group
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
Overview
========

Publish messages to single or multiple queues for processing

"""

import os
import argparse

from inspect import signature

from stoq.scan import get_sha1
from stoq.args import StoqArgs
from stoq.plugins import StoqWorkerPlugin


class PublisherWorker(StoqWorkerPlugin):

    def __init__(self):
        super().__init__()

    def activate(self, stoq):

        self.stoq = stoq

        parser = argparse.ArgumentParser()
        parser = StoqArgs(parser)
        worker_opts = parser.add_argument_group("Plugin Options")
        worker_opts.add_argument("-p", "--priority",
                                 dest='priority',
                                 type=int,
                                 choices=range(0,11),
                                 help="Priority of message")
        worker_opts.add_argument("-w", "--worker",
                                 dest='submission_list',
                                 action='append',
                                 help="Worker queues that should process \
                                       sample. May be used multiple times")
        worker_opts.add_argument("-q", "--publisher",
                                 dest='publisher',
                                 help="Source plugin to publish samples to")

        options = parser.parse_args(self.stoq.argv[2:])

        super().activate(options=options)

        # Activate the appropriate plugin so we can publish messages,
        # if needed.
        self.publish_connector = self.stoq.load_plugin(self.publisher, 'source')

        if not hasattr(self.publish_connector, 'publish'):
            self.log.warn("Plugin does not support publishing to queues")
            return False

        return True

    def scan(self, payload, **kwargs):
        """
        Publish messages to single or multiple RabbitMQ queues for processing

        :param bytes payload: Payload to be published
        :param str path: Path to file being ingested
        :param list submission_list: List of queues to publish to
        :param int priority: Priority of message, if supported by publisher

        :returns: True

        """

        super().scan()

        opts = {}

        # For every file we ingest we are going to assign a unique
        # id so we can link everything across the scope of the ingest.
        # This will be assigned to submissions within archive files as well
        # in order to simplify correlating files post-ingest.
        if 'uuid' not in kwargs:
            kwargs['uuid'] = [self.stoq.get_uuid]

        if payload and 'sha1' not in kwargs:
            kwargs['sha1'] = get_sha1(payload)

        if 'path' in kwargs:
            kwargs['path'] = os.path.abspath(kwargs['path'])
            self.log.info("Ingesting {}".format(kwargs['path']))
        else:
            self.log.info("Ingesting {}".format(kwargs['uuid'][-1]))

        if 'submission_list' in kwargs:
            self.submission_list = kwargs['submission_list']
            kwargs.pop('submission_list')

        # Using self.stoq.worker.archive_connector in case this plugin is
        # called from another plugin. This will ensure that the correct
        # archive connector is defined when the message is published.
        if self.stoq.worker.archive_connector and self.name != self.stoq.worker.name:
            kwargs['archive'] = self.stoq.worker.archive_connector
        elif self.archive_connector:
            kwargs['archive'] = self.archive_connector
        else:
            kwargs['archive'] = "file"

        if 'priority' in kwargs:
            opts['priority'] = int(kwargs['priority'])
            kwargs.pop('priority')
        else:
            opts['priority'] = self.priority

        for routing_key in self.submission_list:
            if 'payload' in signature(self.publish_connector.publish).parameters:
                payload = self.stoq.get_file(kwargs['path'])
                self.publish_connector.publish(kwargs, routing_key, payload=payload, **opts)
            else:
                self.publish_connector.publish(kwargs, routing_key, **opts)

        return True
