#!/usr/bin/env python2
"""
Script for testing the UKF Manager.
Note that this f_main.py does not interface with ROS.
As for the ROS Node, refer to f_ros.py.
"""

from f_utils import *
from f_config import *
import f_config as cfg

import numpy as np
import cv2

from f_manager import UKFManager 
from f_model import TargetRoombaModel, ObstacleRoombaModel

def random_pose():
    x = np.random.uniform(-10.0, 10.0)
    y = np.random.uniform(-10.0, 10.0)
    t = np.random.uniform(-np.pi, np.pi)
    #v = np.abs(np.random.normal(0.27, 0.33))
    v = np.random.uniform(0.27, 0.33)
    w = 0.1 * np.random.choice([-1,1]) * np.random.normal(0.8, 1.2)
    return np.asarray([x,y,t,v,w], dtype=np.float32)

def main():
    # parameters
    n_targets = 20
    dt = 0.01
    steps = (100.0 / dt)
    sigmas = np.asarray([S_X, S_Y, S_T, S_V, S_W])

    # configure models by params
    TargetRoombaModel.configure({
        # speed configurations
        'v'    : 0.33,
        'w'    : 1.375,
        # intervals
        't_n'  : cfg.INT_NOISE, # noise interval
        't_r'  : cfg.INT_REVERSE, # reversal interval
        # durations
        'd_180': cfg.T_180,
        'd_45' : cfg.T_45,
        'd_n'  : cfg.T_NOISE
        })

    ObstacleRoombaModel.configure({
        'v'    : 0.33,
        'w'    : 0.066
        })

    # initialization
    drone = Drone(np.zeros(shape=5, dtype=np.float32))
    targets = [Target(random_pose()) for i in range(n_targets)]

    # render ...
    win_name = 'world'
    render = Renderer(win_name)
    def set_drone_pos(e,x,y,f,p):
        x,y = render._convert_inv(x,y)
        drone._pose[0]=x
        drone._pose[1]=y
    cv2.setMouseCallback(win_name,set_drone_pos)

    # initialize filter manager
    manager = UKFManager(dt, sigmas)
    particles = {}

    #for i, t in enumerate(targets):
    #    # initial estimates with noisy pose
    #    pose = add_noise(t._pose, sigmas)
    #    manager.create(pose)

    t = 3.0
    while True:
        # observations ...
        obs_ar = CircularObservation(
                drone._pose[0],
                drone._pose[1],
                3.0 # TODO : arbitrary, fix
                )
        obs = []

        for r in targets:
            if r._pose in obs_ar:
                p = add_noise(r._pose, s=dt*sigmas)[:3]
                #print p
                #o = r.clone()
                #o._pose = add_noise(r._pose, s=dt*sigmas)
                o = ObservationParticle(
                        pose=p,
                        t=T_NULL,
                        )
                #print o
                obs.append(o)

        # render
        k = render(
                drone._pose,
                [_t._pose for _t in targets],
                manager.estimates().values(),
                t,
                delay=1
                )

        # filter
        manager.step(obs, t, dt, obs_ar)

        # step world
        for _t in targets:
            _t.step(t,dt)

        if k == 27:
            print 'done'
            break
        t += dt

if __name__ == "__main__":
    main()
