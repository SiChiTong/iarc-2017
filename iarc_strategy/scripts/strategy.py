#!/usr/bin/env python2
"""
This file represents the main strategy node.
It takes as input the positions of the Roombas on the field,
and outputs commands to the Arbiter.

Owner: Schommer
"""
import numpy as np
import os
import rospkg
import sys
# from pygraphviz import *
from enum import Enum
import rospy
import tf
import tf.transformations
from geometry_msgs.msg import Twist
from iarc_main.msg import Roomba, RoombaList
from std_msgs.msg import Float64, String

from five_sec_sim import fiveSecSim

rospack = rospkg.RosPack()
iarc_sim_path = rospack.get_path('iarc_sim_2d')
sys.path.append(os.path.join(iarc_sim_path, 'src'))

from config import XY_VEL, Z_VEL, LAND_IN_FRONT_DIST, ROOMBA_HEIGHT


class Action(Enum):
    """
    Action Enum for all possible actions.
    """
    TOP_HIT = 1
    LAND_IN_FRONT = 2
    TOP_HIT_2X = 3
    TOP_HIT_3X = 4
    WAIT = 5


class Drone(object):
    def __init__(self, C1=1, C2=1, C3=1, C4=1, C5=1, MIN_OBSTACLE_DISTANCE=1.5, FIELD_SIZE=20.0):
        self.tf = tf.TransformListener()
        self.tag = 'drone'
        rospy.Subscriber('/seen_roombas', RoombaList, self.recordVisible)
        rospy.Subscriber('/drone/height', Float64, self.recordHeight)
        self.vel3d = Twist()
        self.visibleRoombas = []  # type: list[Roomba]
        self.visibleObstacles = []  # type: list[Roomba]

        self.C1 = C1
        self.C2 = C2
        self.C3 = C3
        self.C4 = C4
        self.C5 = C5
        self.MIN_OBSTACLE_DISTANCE = MIN_OBSTACLE_DISTANCE

        self.FIELD_SIZE = FIELD_SIZE

    def recordVisible(self, msg):
        """
        :param (RoombaList) msg:
        """
        self.visibleRoombas = [x for x in msg.data if x.type in (Roomba.RED, Roomba.GREEN)]
        self.visibleObstacles = [x for x in msg.data if x.type == Roomba.OBSTACLE]

    def recordHeight(self, msg):
        """
        :param (Float64) msg:
        :return:
        """
        self.height = msg.data

    def getPose(self):
        self.drone_pos, self.drone_heading = self.tf.lookupTransform(
            'map', '%s' % drone.tag, rospy.Time(0)
        )

    def actionTimeEstimate(self, target, action):
        """
        Based on the action entered, returns an estimate of how long the
        action will take to execute.
        :param action:
        :param target: Roomba
        :return:
        """
        self.getPose()
        t = 0  # Initialize time estimate

        print(action)
        if action == Action.TOP_HIT:

            x_d = self.drone_pos[0] - target.visible_location.pose.pose.position.x
            y_d = self.drone_pos[1] - target.visible_location.pose.pose.position.y
            d_xy = np.sqrt(x_d ** 2 + y_d ** 2)
            t = d_xy / XY_VEL + 0 * (self.height - ROOMBA_HEIGHT) / Z_VEL
        elif action == Action.LAND_IN_FRONT:
            angle = self.orientationToHeading(target.visible_location.pose.pose.orientation)
            x_d = self.drone_pos[0] - (
                target.visible_location.pose.pose.position.x + LAND_IN_FRONT_DIST * np.cos(angle))
            y_d = self.drone_pos[1] - (
                target.visible_location.pose.pose.position.y + LAND_IN_FRONT_DIST * np.sin(angle))
            d_xy = np.sqrt(x_d ** 2 + y_d ** 2)
            t = d_xy / XY_VEL + 0 * (self.height - ROOMBA_HEIGHT) / Z_VEL

        return t

    def orientationToHeading(self, orientation):
        """
        Converts a quaterion in the form of a pose orientation into a heading.
        :param orientation:
        :return:
        """
        res = [0, 0, 0, 0]
        res[0] = orientation.x
        res[1] = orientation.y
        res[2] = orientation.z
        res[3] = orientation.w
        return tf.transformations.euler_from_quaternion(res)[2]

    def goodnessScore(self):
        """
        Determines which Roomba we pick to lead to the goal.
        Higher score is better.

        Returns: [(Roomba, Score)]
        :rtype list[tuple[Roomba, float]]
        """

        def headingScore(roomba):
            # print(roomba.visible_location.pose.pose.orientation)
            heading = self.orientationToHeading(roomba.visible_location.pose.pose.orientation)

            return np.sin(heading)

        def positionScore(roomba):
            return roomba.visible_location.pose.pose.position.y

        def distanceFromObstaclesScore(roomba, obstacles):
            """
            (-infinity, 0)
            """

            score = 0
            for obstacle in obstacles:
                x = roomba.x - obstacle.x
                y = roomba.y - obstacle.y
                dist = np.sqrt(x ** 2 + y ** 2)

                if dist < MIN_OBSTACLE_DISTANCE:
                    return -math.inf

                score -= 1 / dist ** 2

            return score

        def stateQualtityScore(roomba):
            """
            How precisely we know the Roombas' state.
            Compare position accuracy to view radius to know if it's possible
            to see the given roomba when drone arrives.
            """
            return 0

        def futureGoodnessScore(roomba):
            return 0

        result = []

        for i in xrange(0, len(self.visibleRoombas)):
            roomba = self.visibleRoombas[i]

            score = self.C1 * headingScore(roomba) + \
                    self.C2 * positionScore(roomba) + \
                    self.C3 * distanceFromObstaclesScore(roomba, self.visibleObstacles) + \
                    self.C4 * stateQualtityScore(roomba) + \
                    self.C5 * futureGoodnessScore(roomba)
            result.append((roomba, score))

        return result

    def targetSelect(self, roombaScore):
        # print(roombaScore)
        # print(roombaScore != [])
        if roombaScore != []:
            # return [0,Drone()]
            # print(max(roombaScore, key=lambda x: x[1]))
            return max(roombaScore, key=lambda x: x[1])
        else:
            res = Drone()
            # print("Garb")
            res.tag = ''
            return [res, 0]

    def chooseAction(self, target):
        """
        Determined what the best action to take is for the given target
        :param (Roomba) target: The Roomba we intend to interact with
        :return: The best action to take
        """
        # The maximum angle the target may deviate from North/South for us to want to turn it 45 degrees.
        ANGLE_WINDOW = np.deg2rad(30)
        TURN_TIME = rospy.Duration.from_sec(4.0)

        desired_angle = 0  # Want target going north

        # Step 1: check for a win condition
        roombaWillWin = False
        for dt in range(0, 20, 3):
            prediction = fiveSecSim(target.last_turn, target.visible_location, rospy.Time.now() + rospy.Duration.from_sec(dt))
            if prediction.pose.pose.position.y > self.FIELD_SIZE / 2:
                roombaWillWin = True
                break

        if roombaWillWin:
            return 'follow'

        # Step 2: check for 45 degree turns

        current_angle = tf.transformations.euler_from_quaternion(target.visible_location.pose.pose.orientation)[2]

        angle_delta = self.subtract_angles(desired_angle, current_angle)
        if ANGLE_WINDOW < abs(angle_delta) < np.pi - ANGLE_WINDOW:
            # The roomba is going mostly perpendicular
            return '45'

        # Step 3: check for 180 degree turns
        expected_time = rospy.Time.now() + TURN_TIME
        expected_pos = fiveSecSim(target.last_turn, target.visible_location, expected_time)
        cycle_phase = (expected_time - target.last_turn).to_sec() % 20

        expected_angle = tf.transformations.euler_from_quaternion(expected_pos.pose.pose.orientation)[2]
        angle_delta = self.subtract_angles(desired_angle, expected_angle)

        if abs(angle_delta) > np.pi / 2 and cycle_phase <= 18:
            # The roomba is going the wrong way and not about to turn
            return '180'

        return 'follow'

    @staticmethod
    def subtract_angles(a, b):
        res = a - b

        while res <= -np.pi:
            res += 2 * np.pi
        while res > np.pi:
            res -= 2 * np.pi

        return res


class DroneCommander(object):
    """
    A DroneCommander is responsible for sending commands
    that control the behavior of the drone by directly commanding the Arbiter."""
    def __init__(self):
        self._behavior_pub = rospy.Publisher('/arbiter/activate_behavior', String, queue_size=10)
        self._target_pub = rospy.Publisher('/target', Roomba, queue_size=10)

    def output(self, behavior, target=None):
        """
        :param str behavior: One of "teleop", "follow", or "landinfront"
        :param (Roomba) target:
        :return:
        """

        if behavior not in ['zero', 'follow', 'landinfront', 'teleop']:
            raise Exception('Illegal behavior commanded: {}'.format(behavior))

        # landinfront has not been implemented yet, fall back to following
        if behavior == 'landinfront':
            rospy.logerr_throttle(5, "landinfront not implemented, following instead")
            behavior = 'follow'

        self._behavior_pub.publish(behavior)

        if target:
            self._target_pub.publish(target)


if __name__ == '__main__':
    rospy.init_node('strategy')

    drone = Drone()
    commander = DroneCommander()
    r = rospy.Rate(10)
    last_valid_time = rospy.Time(0)

    rospy.on_shutdown(lambda: commander.output('teleop'))

    while not rospy.is_shutdown():
        r.sleep()
        print('_' * 80)
        # print(drone.goodnessScore())
        scoresList = drone.goodnessScore()
        if len(scoresList) > 0:
            last_valid_time = rospy.Time.now()
            for roomba, score in scoresList:
                # print(score)
                # drone.actionTimeEstimate(roomba, Action.LANDINFRONT)
                print('score: %f roomba: %s' % (score, roomba.frame_id))

            bestRoomba, bestRoombaScore = drone.targetSelect(scoresList)
            print('Best Score: %f Best Roomba: %s' % (bestRoombaScore, bestRoomba.frame_id))

            # TODO: use drone.chooseAction to pick what behavior is best, rather than following unconditionally
            commander.output('follow', bestRoomba)
        else:
            print "No Roombas found"
            if rospy.Time.now() - last_valid_time > rospy.Duration.from_sec(5.0):
                print "Falling back to teleop mode"
                # TODO: this should fall back to search mode of some sort
                commander.output('teleop')

    exit()
