#   Copyright 2014-2015 PUNCH Cyber Analytics Group
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

Publish and Consume messages from a RabbitMQ Server

"""

from kombu.pools import producers
from kombu import Connection, Consumer, Exchange, Queue

from stoq.plugins import StoqSourcePlugin


class RabbitMQSource(StoqSourcePlugin):

    def __init__(self):
        super().__init__()

    def activate(self, stoq):
        self.stoq = stoq

        super().activate()

        self.amqp_publish_conn = None

    def ingest(self):
        """
        Monitor AMQP for messages

        """

        if self.stoq.worker.name:
            # Define our RabbitMQ route
            routing_key = self.stoq.worker.name

            # If this is an error message, let's make sure our queue
            # has "-errors" affixed to it
            if self.stoq.worker.error_queue is True:
                routing_key = routing_key + "-errors".strip()

            exchange = Exchange(self.exchange_name, type=self.exchange_type)
            queue = Queue(routing_key, exchange, routing_key=routing_key)

            # Setup our broker connection with RabbitMQ
            with Connection(hostname=self.host,
                            port=self.port,
                            userid=self.user,
                            password=self.password,
                            virtual_host=self.virtual_host) as conn:

                consumer = Consumer(conn, queue,
                                    callbacks=[self.queue_callback])
                consumer.qos(prefetch_count=int(self.prefetch))
                consumer.consume()

                while True:
                    conn.drain_events()
        else:
            self.stoq.log.error("No worker name defined!")

    def queue_callback(self, amqp_message_data, amqp_message_handler):
        try:
            # Setup the amqp message for parsing
            kwargs = self.stoq.loads(amqp_message_data)

            # Send the message to the worker
            self.stoq.worker.start(**kwargs)

        except Exception as e:
            # Something went wrong, let's publish to the error queue.  and
            # append the error message.
            kwargs['err'] = str(e)
            self.stoq.log.error(kwargs)
            self.publish_connect()
            self.publish(kwargs, self.stoq.worker.name, err=True)
            self.publish_release()

        # Acknowledge our message in amqp so we can get the next one.
        amqp_message_handler.ack()

    def publish_connect(self):
        """
        Connect to AMQP to publish a message

        :returns: AMQP connection object for publishing
        :rtype: kombu.Connection object

        """
        self.amqp_exchange = Exchange(self.exchange_name,
                                      type=self.exchange_type)

        self.amqp_publish_conn = Connection(hostname=self.host,
                                            port=self.port,
                                            userid=self.user,
                                            password=self.password,
                                            virtual_host=self.virtual_host)
        return self.amqp_publish_conn

    def publish_release(self):
        """
        Release AMQP connection used for publishing

        """
        return self.amqp_publish_conn.release()

    def publish(self, msg, routing_key, err=False):
        """
        Publish a message to AMQP

        :param dict msg: Message to be published, preferrably json
        :param bytes routing_key: Route to be used, should be name of worker
        :param err err: Define whether we should process error queue

        """

        # Make sure we have a valid connection to RabbitMQ
        if not self.amqp_publish_conn:
            self.publish_connect()

        # If this is an error message, let's make sure our queue
        # has "-errors" affixed to it
        if err:
            routing_key = routing_key + "-errors".strip()

        # Define the queue so we can ensure it is declared before
        # publishing to it
        queue = Queue(routing_key, self.amqp_exchange, routing_key=routing_key)

        with producers[self.amqp_publish_conn].acquire(block=True) as producer:
            producer.publish(self.stoq.dumps(msg),
                             exchange=self.amqp_exchange,
                             declare=[self.amqp_exchange, queue],
                             routing_key=routing_key)

    def __errback(self, exc, interval):
        """
        Error handling for AMQP publishing

        """
        self.stoq.log.warn("Unable to publish message: {}. Retry in {}s.".format(
                           exc, interval))
