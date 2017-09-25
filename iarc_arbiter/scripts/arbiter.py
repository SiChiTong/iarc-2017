#!/usr/bin/env python2
import rospy
from geometry_msgs.msg import Twist
from std_msgs.msg import Empty, String
from iarc_arbiter.srv import *

import transformers

rospy.init_node('arbiter')


class Arbiter:
    def __init__(self):
        null_behavior = Behavior('null', self, friendly_name='Undefined behavior', is_magic=True)

        self.behaviors = [null_behavior]
        self.active_behavior = null_behavior
        self.choose_leader()

        # Transformers are functions capable of processing incoming data in a variety of formats.
        self.transformers = {
            'raw_cmd_vel': (Twist, transformers.raw_cmd_vel),
            'cmd_vel': (Twist, transformers.cmd_vel),
        }

        self.secondaries = []

        self.vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=0)
        self.takeoff_pub = rospy.Publisher('/ardrone/takeoff', Empty, queue_size=10)
        self.land_pub = rospy.Publisher('/ardrone/land', Empty, queue_size=10)

        self.status_pub = rospy.Publisher('status', String, queue_size=10)
        self.active_pub = rospy.Publisher('active_behavior', String, queue_size=10)

        rospy.Service('register', Register, self.handle_register)

    def handle_register(self, req):
        """
        :type req: RegisterRequest
        """
        print req
        if not req.namespace:
            rospy.logerr("Service cannot be created with empty namespace")
            return

        if not req.name:
            req.name = req.namespace.strip('/')

        if not req.pretty_name:
            req.pretty_name = req.name

        behavior = Behavior(req.name, self, req.namespace, req.pretty_name)
        self.behaviors.append(behavior)
        rospy.loginfo("Created behavior {}".format(behavior))

        return RegisterResponse(name=behavior.name)

    def subscribe_all(self):
        for b in self.behaviors:
            if b.is_magic or b.namespace in (None, '', '/'):
                # This behavior is internal to the arbiter, and should not be subscribed.
                continue

            topics = rospy.get_published_topics(b.namespace)
            for t in topics:
                name = t[0][len(b.namespace):].strip('/')
                if name in self.transformers and name not in b.subscribers:
                    b.subscribe(name)

    def process_command(self, behavior, cmd):
        """
        process_command gets called after a message gets received from the currently active behavior.

        :param behavior: The behavior initiating the request
        :type cmd: transformers.Command
        """

        for func in self.secondaries:
            cmd = func(cmd)

        if cmd.takeoff:
            self.takeoff_pub.publish(Empty())
            self.vel_pub.publish(Twist())
        elif cmd.land:
            self.land_pub.publish(Empty())
            self.vel_pub.publish(Twist())
        else:
            self.vel_pub.publish(cmd.vel)

        self.active_pub.publish(String(behavior.name))
        rospy.loginfo_throttle(1, "Command published by {}".format(behavior.name))

    def choose_leader(self):
        # TODO: placeholder, make votes and stuff count
        self.active_behavior.is_leader = False
        self.active_behavior = self.behaviors[-1]
        self.active_behavior.is_leader = True

    def publish_status(self):
        self.status_pub.publish(String(str(self.behaviors)))

    def run(self):
        r_vote = rospy.Rate(20)
        r_scan = rospy.Rate(1)

        while not rospy.is_shutdown():
            self.choose_leader()
            self.publish_status()

            if r_scan.remaining() < rospy.Duration(0):
                self.subscribe_all()
                r_scan.sleep()

            r_vote.sleep()


class Behavior:
    def __init__(self, name, arbiter, namespace=None, friendly_name=None, intrinsic_vote=0, is_magic=False):
        if friendly_name is None:
            friendly_name = name
        if namespace is None:
            namespace = name
        if namespace[0] != '/':
            namespace = '/' + namespace

        self.name = name
        self.arbiter = arbiter
        self.namespace = namespace
        self.friendly_name = friendly_name
        self.intrinsic_vote = intrinsic_vote
        self.is_magic = is_magic
        self.subscribers = dict()

        self.is_leader = False
        self.last_msg_time = rospy.Time(0)

    def handle_message(self, topic, msg):
        msg_type, transformer = self.arbiter.transformers[topic]

        self.last_msg_time = rospy.Time.now()
        if self.is_leader:
            standardized = transformer(msg)
            self.arbiter.process_command(self, standardized)

    def subscribe(self, topic):
        if topic not in self.arbiter.transformers:
            rospy.logerr_throttle(1, "Unable to subscribe to topic {} for {}: unknown type".format(topic, self.name))
            return

        msg_type, transformer = self.arbiter.transformers[topic]

        def callback(msg):
            self.handle_message(topic, msg)

        sub = rospy.Subscriber("{}/{}".format(self.namespace, topic), msg_type, callback)
        self.subscribers[topic] = sub

        rospy.loginfo("Subscribed to {}/{}".format(self.namespace, topic))


if __name__ == '__main__':
    Arbiter().run()