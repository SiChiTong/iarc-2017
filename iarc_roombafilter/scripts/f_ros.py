#!/usr/bin/env python2

"""
ROS Interface to the Multi-Target Matching UKF Filter.
Configuration files should be modified under f_config.py

Takes RoombaObservation and filters them into pose.

TODO(yoonyoungcho) : expose dynamic_reconfigure
TODO(yoonyoungcho) : convert dt
TODO(yoonyoungcho) : verify fovcenter ~= Drone Position?
TODO(yoonyoungcho) : is model-based predictive simulation necessary?
TODO(yoonyoungcho) : resolve iterative prediction vs. sparse updates
"""

import rospy

from std_msgs.msg import Header
from geometry_msgs.msg import Pose, PoseStamped, PoseWithCovariance, PoseWithCovarianceStamped
from geometry_msgs.msg import Point, Quaternion

from iarc_main.msg import Roomba, RoombaSighting, RoombaList
import tf

# Filter-Related ...
from f_utils import *
import f_config as cfg
import numpy as np
import cv2

from f_manager import UKFManager

class UKFManagerROS(object):
    def __init__(self, dt):

        # unroll parameters ...
        self._max_targets = rospy.get_param('~max_targets', default=30)
        self._sigma = rospy.get_param('~sigma', default=list(cfg.SIGMAS))
        self._p_keep = rospy.get_param('~p_keep', default=cfg.P_KEEP)
        self._p_match = rospy.get_param('~p_match', default=cfg.P_MATCH)
        self._p_clear = rospy.get_param('~p_clear', default=cfg.P_CLEAR)
        self._obs_topic = rospy.get_param('~obs_topic', default='roomba_obs')
        self._rate = rospy.get_param('~rate', default=100)

        # create ROS interfaces
        self._tf = tf.TransformListener()
        self._sub = rospy.Subscriber(self._obs_topic, RoombaSighting, self.obs_cb)
        self._pub = rospy.Publisher('roombas', RoombaList, queue_size=10)
        self._mgr = UKFManager(dt, self._sigma)
        self._t = rospy.Time.now()

    def obs_cb(self, msg):
        """
        Perform filtering according to observation.
        """
        pos = self._tf.transformPoint('map', msg.fov_center)
        obs_ar = CircularObservation(
                pos.point.x,
                pos.point.y,
                msg.fov_radius
                )

        # format observation data ...
        obs = []
        for r in msg.data:
            p = PoseStamped(r.visible_location.header, r.visible_location.pose.pose)
            p = self._tf.transformPose('map', p).pose
            p, q = p.position, p.orientation
            h = tf.transformations.euler_from_quaternion([q.x,q.y,q.z,q.w])[2]
            pose = [p.x, p.y, h, 0, 0]
            # TODO(yoonyoungcho) : is current code handling NaN well?

            # roomba type handling
            r_type = cfg.T_NULL
            r_col = cfg.C_NULL
            if r.type != Roomba.UNKNOWN:
                if r.type == Roomba.OBSTACLE:
                    r_type = cfg.T_OBST
                else:
                    r_type = cfg.T_TARG
                    r_col = (cfg.C_RED if r.type == Roomba.RED else cfg.C_GREEN)
            
            o = ObservationParticle(
                    pose=pose,
                    t=r_type,
                    c=r_col
                    )
            obs.append(o)

        # TODO(yoonyoungcho) does filterpy support retrodictive updates?
        # TODO(yoonyoungcho) t = t0+dt or t1-dt?
        t = msg.header.stamp.to_sec()
        self._mgr.step(obs, t, t-self._t, obs_ar)

    def publish(self):
        now = rospy.Time.now()
        cov = np.eye(6) * 1e-6 # TODO : do real covs
        cov = cov.flatten()
        msgs = []
        for e in self._mgr.estimates():
            (x,y,t,v,w) = e._pose
            s,c = np.sin(t/2.0), np.cos(t/2.0)
            p = Point(x,y,0)
            q = Quaternion(0,0,s,c)
            loc = PoseWithCovarianceStamped(
                    Header(stamp=now, frame_id="map"),
                    PoseWithCovariance(
                        Pose(p,q),
                        cov
                    ))
            msg = Roomba(now, "map", Roomba.UNKNOWN, loc)
            msgs.append(msg)
        msg = RoombaList(Header(stamp=now,frame_id="map"), msgs)
        self._pub.publish(msg)

    def run(self):
        rate = rospy.Rate(self._rate)
        while not rospy.is_shutdown():
            self._t = rospy.Time.now().to_sec()
            self.publish()
            rate.sleep()


def main():
    rospy.init_node('roomba_filter')
    # TODO : fix dt / sigmas instantiation
    mgr = UKFManagerROS(dt=1e-3)
    mgr.run()

if __name__ == "__main__":
    main()
