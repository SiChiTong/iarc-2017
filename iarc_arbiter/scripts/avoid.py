#!/usr/bin/env python
import numpy as np

import rospy
from geometry_msgs.msg import Vector3Stamped
from tf import TransformListener

from transformers import Command


class AvoidBehavior:
    def __init__(self, tf):
        """
        :type tf: TransformListener
        """
        self.tf = tf
        self.obstacles = []  # array of (x,y,z) positions of obstacles in base_link
        # Wait until the transformListener initialize
        rospy.sleep(0.5)
        self.pos = [0, 0, 0]
        if self.tf.canTransform('base_link', 'map', rospy.Time(0)):
            # TODO In the future, Vector3 will be Vector3[], to accomodate multiple obstacles
            self.obstacles_sub = rospy.Subscriber('/base_link/obstacles', Vector3Stamped, self.update_obstacles)

            # TODO: Subscribe to actual velocity now and update self.vel in baselink
            # TODO: get self's absolute position now

    def update_obstacles(self, msg):
        self.obstacles.append((msg.vector.x, msg.vector.y, msg.vector.z))

    def avoid_obstacles(self, input_cmd):
        """
        :type input_cmd: Command
        :rtype: Command
        """
        output_cmd = input_cmd.copy()

        if len(self.obstacles) > 2 and self.pos[2] < 2:
            # Set vz to be positive if there are more than 2 obstacles and we're below 2m
            output_cmd.vel.linear.z = 1
        directions = np.zeros(360)  # Array of length 360 that stores how preferable is each direction (deg)

        # TODO:Add around the cmd velocity direction a positive normal distribution

        for obst in self.obstacles:
            obst_dist = np.sqrt(obst[0] ** 2 + obst[1] ** 2)
            # TODO: convert obstacle position to angles
            # subract a normal distribution centered at the obstacle angle in the directions array
            # Determine the magnitude of subtraction by e^(-1/v*(x-1)), where x is obst_dist
            # Take in a rosparam for the width of the normal distribution

        # maxvelocity of our drone
        maxvelocity = rospy.get_param('~max_velocity', 1.0)
        kpturn = rospy.get_param('~kp_turn', 2)

        return output_cmd


if __name__ == '__main__':
    rospy.init_node('AvoidBehavior')
    tfl = TransformListener()
    AvoidBehavior(tfl)
