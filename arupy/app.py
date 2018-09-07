#!/usr/bin/env python3
# coding:utf-8
import traceback
import time
import pika
import threading
from . import config, outils

logger = outils.get_logger('arupy')


class ArupyError(Exception):
    """"""
    pass


class Arupy(threading.Thread):
    """"""

    def __init__(self, configfile="config.yml"):
        """Constructor"""
        threading.Thread.__init__(self, name="arupy-main")
        self.daemon = True

        self.pika_params = config.parse_mq_parameters_from_file(configfile)
        self.is_working = threading.Event()
        self.consumers = {}
        self.connection = None

    def run(self):
        self.is_working.set()
        logger.info('arupy is started.')
        while self.is_working.isSet():
            try:
                if not self.connection:
                    self.connection = pika.BlockingConnection(self.pika_params)
                    logger.info('arupy is connected to mq: {}.'.format(self.pika_params))
            except:
                logger.warn("arupy connection is failed. try 3s later")
                self.connection = None
                time.sleep(3)
                continue

            try:
                self.channel = self.connection.channel()
                logger.info('arupy created a channel.')
            except:
                logger.warn("create channel failed. retry 3s later")
                if self.connection:
                    self.connection.sleep(3)
                else:
                    time.sleep(3)

            try:
                logger.info("initializing consumers")
                self.initial_consumers()
                logger.info('init consumers succeeded.')
            except Exception:
                logger.warn("errors in initial consumer: {}".format(
                    traceback.format_exc()
                ))
                raise ArupyError()

            try:
                logger.info("set qos to 1")
                self.channel.basic_qos(prefetch_count=1)
            except:
                logger.warn('set qos failed.')

            try:
                self.channel.start_consuming()
                break
            except Exception:
                logger.warn("unexpect exit when consuming. {}".format(traceback.format_exc()))

        self.is_working.clear()
        logger.info("Arupy is shutdown normally.")

    def add_consumer(self, consumer_kls):
        consumer = consumer_kls(self)
        if consumer.queue_name not in self.consumers:
            logger.info('consumer: {} is added.'.format(consumer_kls))
            self.consumers[consumer.queue_name] = consumer
        else:
            raise ValueError("the queue_name: {} is existed in consumers")

    def new_publisher(self):
        return ArupyPublisher(self.pika_params)

    def initial_consumers(self):
        def _(qname, consumer):
            consumer.on_channel_creaetd(self.channel)
            logger.info("set consumer for queue name: {}".format(qname))
            self.channel.basic_consume(consumer.handle, qname, consumer_tag=qname)
        [_(qname, consumer) for (qname, consumer) in self.consumers.items()]

    def serve_until_no_consumers(self):
        while self.consumers:
            self.is_working.wait(1)

    def remove_consumer(self, qname):
        self.channel.basic_cancel(consumer_tag=qname)
        logger.info("cancel consumer for queue: {}".format(qname))
        self.consumers.pop(qname, None)

    def stop(self):
        try:
            self.channel.stop_consuming()
            logger.info("stop consuming succeeded.")
        except:
            logger.info("stop consuming failed.")

        if self.is_working.isSet():
            self.is_working.clear()

        try:
            self.channel.close()
            logger.info("close channel succeeded")
        except:
            pass

        try:
            self.connection.close()
            logger.info("close pika connection succeeded")
        except:
            pass


class ArupyConsumer(object):
    """"""

    queue_name = "default"

    def __init__(self, app: Arupy):
        """Constructor"""
        self.app = app

    def on_channel_creaetd(self, channel):
        pass

    def handle(self):
        pass


class ArupyPublisher(object):
    """"""

    def __init__(self, pika_params):
        """Constructor"""
        self.params = pika_params
        self.conn = pika.BlockingConnection(self.params)
        self.chan = self.conn.channel()

    def publish(self, exchange, routing_key, body, properties=None, mandatory=False, immediate=False):
        self.chan.basic_publish(exchange, routing_key, body, properties, mandatory, immediate)

    def close(self):
        self.chan.close()
        self.conn.close()

