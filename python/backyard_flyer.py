# -*- coding: utf-8 -*-
"""
Solution to the Backyard Flyer Project.
"""

import time
from enum import Enum

import numpy as np

from udacidrone import Drone
from unity_drone import UnityDrone
from controller import NonlinearController
from udacidrone.connection import MavlinkConnection, WebSocketConnection  # noqa: F401
from udacidrone.messaging import MsgID  

import visdom


class States(Enum):
    MANUAL = 0
    ARMING = 1
    TAKEOFF = 2
    WAYPOINT = 3
    LANDING = 4
    DISARMING = 5


class BackyardFlyer(UnityDrone):

    def __init__(self, connection):
        super().__init__(connection)
        self.target_position = np.array([0.0, 0.0, 0.0])
        self.all_waypoints = []
        self.in_mission = True
        self.check_state = {}

        self.controller = NonlinearController()

        # initial state
        self.flight_state = States.MANUAL

        # register all your callbacks here
        self.register_callback(MsgID.LOCAL_POSITION, self.local_position_callback)
        self.register_callback(MsgID.LOCAL_VELOCITY, self.velocity_callback)    
        self.register_callback(MsgID.STATE, self.state_callback)

        self.register_callback(MsgID.ATTITUDE, self.attitude_callback)
        self.register_callback(MsgID.RAW_GYROSCOPE, self.gyro_callback)


        # default opens up to http://localhost:8097
        # self.v = visdom.Visdom()

    #    # Plot NE
    #     ne = np.array(self.local_position[:2]).reshape(-1, 2)

    #     self.ne_plot = self.v.scatter(ne, opts=dict(
    #         title="Local position (north, east)", 
    #         xlabel='North', 
    #         ylabel='East'
    #     ))

    #     # Plot D
    #     d = np.array([self.local_position[2]])        
    #     self.t = 1
    #     print(d.ndim) 
    #     self.d_plot = self.v.line(d, X=np.array([self.t]), opts=dict(
    #         title="Altitude (meters)", 
    #         xlabel='Timestep', 
    #         ylabel='Down'
    #     ))        
            
    #     # for plotting realtime NEO data with visdom
    #     self.register_callback(MsgID.LOCAL_POSITION, self.update_ne_plot)
    #     self.register_callback(MsgID.LOCAL_POSITION, self.update_d_plot)

    # # for plotting realtime NEO data with visdom
    # def update_ne_plot(self):
    #     ne = np.array([self.local_position[0], self.local_position[1]]).reshape(-1, 2)
    #     self.v.scatter(ne, win=self.ne_plot, update='append')

    # # for plotting realtime NEO data with visdom
    # def update_d_plot(self):
    #     d = -np.array([self.local_position[2]])
    #     # update timestep
    #     self.t += 1    
    #     self.v.line(d, X=np.array([self.t]), win=self.d_plot, update='append')        


    def attitude_callback(self):

        if self.flight_state == States.WAYPOINT:
            self.attitude_controller()          

    def gyro_callback(self):
        if self.flight_state == States.WAYPOINT:
            self.bodyrate_controller()

    def local_position_callback(self):
        if self.flight_state == States.TAKEOFF:
            if -1.0 * self.local_position[2] > 0.95 * self.target_position[2]:
                # self.all_waypoints = self.calculate_box()
                (self.position_trajectory, self.time_trajectory, self.yaw_trajectory) = self.load_test_trajectory(time_mult=0.5)
                self.all_waypoints = self.position_trajectory.copy()
                self.waypoint_number = -1                
                self.waypoint_transition()
        elif self.flight_state == States.WAYPOINT:
            # if np.linalg.norm(self.target_position[0:2] - self.local_position[0:2]) < 1.0:
            if time.time() > self.time_trajectory[self.waypoint_number]:
                if len(self.all_waypoints) > 0:
                    self.waypoint_transition()
                else:
                    if np.linalg.norm(self.local_velocity[0:2]) < 1.0:
                        self.landing_transition()

    def velocity_callback(self):
        if self.flight_state == States.LANDING:
            if self.global_position[2] - self.global_home[2] < 0.1:
                if abs(self.local_position[2]) < 0.01:
                    self.disarming_transition()
        if self.flight_state == States.WAYPOINT:
            self.position_controller()

    def state_callback(self):
        if self.in_mission:
            if self.flight_state == States.MANUAL:
                self.arming_transition()
            elif self.flight_state == States.ARMING:
                if self.armed:
                    self.takeoff_transition()
            elif self.flight_state == States.DISARMING:
                if ~self.armed & ~self.guided:
                    self.manual_transition()

    # def calculate_box(self):
    #     print("Setting Home")
    #     local_waypoints = [[10.0, 0.0, 3.0], [10.0, 10.0, 3.0], [0.0, 10.0, 3.0], [0.0, 0.0, 3.0]]
    #     return local_waypoints

    def arming_transition(self):
        print("arming transition")
        self.take_control()
        self.arm()
        self.set_home_position(self.global_position[0], self.global_position[1],
                               self.global_position[2])  # set the current location to be the home position

        self.flight_state = States.ARMING

    def takeoff_transition(self):
        print("takeoff transition")
        # self.global_home = np.copy(self.global_position)  # can't write to this variable!
        target_altitude = 3.0
        self.target_position[2] = target_altitude
        self.takeoff(target_altitude)
        self.flight_state = States.TAKEOFF

    def waypoint_transition(self):
        print("waypoint transition")
        self.target_position = self.all_waypoints.pop(0)
        print('target position', self.target_position)
        # self.cmd_position(self.target_position[0], self.target_position[1], self.target_position[2], 0.0)

        self.local_position_target = np.array((self.target_position[0], self.target_position[1], self.target_position[2]))
        #self.local_position_target = np.array([0.0, 0.0, -3.0])        
        self.flight_state = States.WAYPOINT
        self.waypoint_number = self.waypoint_number+1

    def landing_transition(self):
        print("landing transition")
        self.land()
        self.flight_state = States.LANDING

    def disarming_transition(self):
        print("disarm transition")
        self.disarm()
        self.release_control()
        self.flight_state = States.DISARMING

    def manual_transition(self):
        print("manual transition")
        self.stop()
        self.in_mission = False
        self.flight_state = States.MANUAL

    def start(self):
        self.start_log("Logs", "NavLog.txt")
        # self.connect()

        print("starting connection")
        # self.connection.start()

        super().start()

        # Only required if they do threaded
        # while self.in_mission:
        #    pass

        self.stop_log()

    def position_controller(self):
        """Sets the local acceleration target using the local position and local velocity"""

        (self.local_position_target, self.local_velocity_target, yaw_cmd) = self.controller.trajectory_control(self.position_trajectory, self.yaw_trajectory, self.time_trajectory, time.time())
        self.attitude_target = np.array((0.0, 0.0, yaw_cmd))

        acceleration_cmd = self.controller.lateral_position_control(self.local_position_target[0:2], self.local_velocity_target[0:2], self.local_position[0:2], self.local_velocity[0:2])
        self.local_acceleration_target = np.array([acceleration_cmd[0], acceleration_cmd[1], 0.0])

    def attitude_controller(self):
        """Sets the body rate target using the acceleration target and attitude"""
        self.thrust_cmd = self.controller.altitude_control(-self.local_position_target[2], -self.local_velocity_target[2], -self.local_position[2], -self.local_velocity[2], self.attitude, 9.81)
        roll_pitch_rate_cmd = self.controller.roll_pitch_controller(self.local_acceleration_target[0:2], self.attitude, self.thrust_cmd)
        yawrate_cmd = self.controller.yaw_control(self.attitude_target[2], self.attitude[2])
        self.body_rate_target = np.array([roll_pitch_rate_cmd[0], roll_pitch_rate_cmd[1], yawrate_cmd])

    def bodyrate_controller(self):  
        """Commands a moment to the vehicle using the body rate target and body rates"""
        moment_cmd = self.controller.body_rate_control(self.body_rate_target, self.gyro_raw)
        self.cmd_moment(moment_cmd[0], moment_cmd[1], moment_cmd[2], self.thrust_cmd)        

if __name__ == "__main__":
    conn = MavlinkConnection('tcp:127.0.0.1:5760', threaded=False, PX4=False)
    #conn = WebSocketConnection('ws://127.0.0.1:5760')
    drone = BackyardFlyer(conn)
    drone.test_trajectory_file = './test_trajectory.txt'  
    # drone.test_trajectory_file = './trajectories/stay_there.txt'    
    time.sleep(2)
    drone.start()
    drone.print_mission_score()    