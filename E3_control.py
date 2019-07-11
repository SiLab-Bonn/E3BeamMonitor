''' Communication with ELSA control system for E3 low current beam monitor'''


import zmq
import logging
from basil.dut import Dut
from pybar.run_manager import RunManager
from pybar.scans.tune_gdac import GdacTuning
from pybar.scans.tune_tdac import TdacTuning
from pybar.scans.scan_analog import AnalogScan
from pybar.scans.scan_digital import DigitalScan
from pybar.scans.tune_noise_occupancy import NoiseOccupancyTuning
from pybar.scans.tune_stuck_pixel import StuckPixelTuning
from pybar.scans.scan_fei4_self_trigger import Fei4SelfTriggerScan
import datetime
import time
from pybar.daq.readout_utils import is_data_record, get_col_row_array_from_data_record_array
import numpy as np
from pybar_fei4_interpreter import analysis_utils as fast_analysis_utils
import zlib
import cPickle as pickle

conf = {
    "port_slow_control":5000,
    "port_hit_map":5002,
    }

# global variables
global_vars = {
    "hits":[],
    "baseline":[],
    "coloumn":[],
    "row":[],
    "hist_occ": None,
    "timestamp_start":[],
    "integration_time": .1,
    "hitrate":[],
    "beam":True,
    "analyze":True
    }

from pybar.daq import fifo_readout


run_conf = {"scan_timeout": None,
            "no_data_timeout": None,
            "reset_rx_on_error": False,
            }

tuning_conf = {"target_threshold": 54}


context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://127.0.0.1:%s" % conf["port_slow_control"])

context2 = zmq.Context()
socket2 = context2.socket(zmq.PUB)
socket2.bind("tcp://127.0.0.1:%s" % conf["port_hit_map"])

# get notified if TTi are not working
try:
    from power_supply import power_off, power_on, voltage_channel1, voltage_channel2
except (SystemExit,):
    raise
except Exception:
    logging.error("Failed to connect to TTi", exc_info=True)
    socket.send("Failed to connect to TTi")
   
runmngr = RunManager("/home/rasmus/git/pyBAR/pybar/configuration.yaml")

def skip(raw_data):
    pass

def get_status():
    if runmngr.current_run:
        return runmngr.current_run.get_run_status()

     
def add_done_message():
    if runmngr.current_run:
        socket.send("Scan finished: %s" % runmngr.current_run.run_id)

        
def main():
# should alwayz run no blocking    
    while True:  
        msg = socket.recv()
        
        if get_status() != "RUNNING" and msg == "init":
            try:
                socket.send("start initializing")
                power_on()
                socket.send_string("voltage channel 1 = %s " % voltage_channel1())
                socket.send_string("voltage channel 2 = %s " % voltage_channel2())
                DigitalScan.analyze=skip
                DigitalScan.handle_data = handle_data
                runmngr.run_run(run=DigitalScan,)
            except (SystemExit,):
                raise
            except Exception:
                logging.error("Failed to initialize", exc_info=True)
                socket.send("Failed to initialize")
            add_done_message()
                
        if get_status() != "RUNNING" and msg == "START":
            fifo_readout.WRITE_INTERVAL = 0.05
            Fei4SelfTriggerScan.run_conf = run_conf
            Fei4SelfTriggerScan.handle_data = handle_data
            runmngr.run_run(run=Fei4SelfTriggerScan, run_conf=run_conf, use_thread=True)
            time.sleep(1)
            #status = get_status()
            socket.send("%s" % runmngr.current_run.run_id)
            socket.send(get_status())
            
        if get_status() == "RUNNING" and msg == "STOP":
            fifo_readout.WRITE_INTERVAL = 1
            runmngr.cancel_current_run(msg)
            socket.send("%s Run Stopped" % runmngr.current_run.run_id)
    
        if msg == "exit":
            if get_status() == "RUNNING":
                runmngr.cancel_current_run(msg)
                socket.send("%s Run Stopped" % runmngr.current_run.run_id)
            logging.info("Program terminates")
            socket.send("Program terminates")
            break
            
        if get_status() != "RUNNING" and msg == "TUNE":

            socket.send("Start GdacTuning")
            GdacTuning.handle_data = handle_data
            runmngr.run_run(GdacTuning,run_conf=tuning_conf, use_thread=True)
            while True:
                time.sleep(1)
                try:
                    msg = socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again: 
                    pass
                if get_status() == "FINISHED" and runmngr.current_run.run_id != "tdac_tuning":
                    add_done_message()
                    socket.send("Start TdacTuning")
                    TdacTuning.handle_data = handle_data
                    runmngr.run_run(TdacTuning,run_conf=tuning_conf, use_thread=True)   
                if msg == "STOP":
                    runmngr.cancel_current_run(msg)
                    socket.send("%s Run Stopped" % runmngr.current_run.run_id)
                    break
                if msg == "status":
                    socket.send_string("voltage channel 1 = %s" % voltage_channel1())
                    socket.send_string("voltage channel 2 = %s" % voltage_channel2())   
                    status = get_status()
                    socket.send(runmngr.current_run.run_id)
                    msg = None
                    if status == None:
                        socket.send("Status=None")
                    else:
                        socket.send(status) 
                if get_status() == "FINISHED" and runmngr.current_run.run_id == "tdac_tuning":
                    add_done_message()
                    break

        if get_status() != "RUNNING" and msg == "sanalog":
            socket.send("Start Analog Scan")
            AnalogScan.analyze=skip
            AnalogScan.handle_data = handle_data
            runmngr.run_run(AnalogScan, use_thread=True)
   
        if get_status() != "RUNNING" and msg == "sdigital":
            socket.send("Start Digital Scan")
            DigitalScan.analyze=skip
            DigitalScan.handle_data = handle_data
            runmngr.run_run(DigitalScan, use_thread=True)
            
        if msg == "poweron":
            power_on()
            socket.send_string("voltage channel 1 = %s " % voltage_channel1())
            socket.send_string("voltage channel 2 = %s " % voltage_channel2()) 
             
        if msg == "poweroff":
            power_off()
            socket.send_string("voltage channel 1 = %s " % voltage_channel1())
            socket.send_string("voltage channel 2 = %s " % voltage_channel2()) 
    
        if msg == "status":
            socket.send_string("voltage channel 1 = %s" % voltage_channel1())
            socket.send_string("voltage channel 2 = %s" % voltage_channel2())   
            status = get_status()
            socket.send(runmngr.current_run.run_id)
            if status == None:
                socket.send("Status=None")
            else:
                socket.send(status)
            if runmngr.current_run.run_id == "fei4_self_trigger_scan":    
                socket.send("hitrate: %.0f [Hz]" % global_vars["hitrate"][-1])
                if len(global_vars["coloumn"])>0:
                    socket.send("Beamspot: %s pixels" % [int(global_vars["coloumn"][-1]),int(global_vars["row"][-1])])
                
        if get_status() != "RUNNING" and msg == "fix":
            socket.send("starting Noise Occupancy Tuning (~2min)")
            runmngr.run_run(NoiseOccupancyTuning, use_thread=True)
            while True:
                time.sleep(1)
                try:
                    msg = socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again: 
                    pass
                if get_status() == "FINISHED" and runmngr.current_run.run_id != "stuck_pixel_tuning":
                    add_done_message()
                    socket.send("starting StuckPixelTuning")
                    runmngr.run_run(StuckPixelTuning, use_thread=True)
                if msg == "STOP":
                    runmngr.cancel_current_run(msg)
                    socket.send("%s Run Stopped" % runmngr.current_run.run_id)
                    break
                if msg == "status":
                    socket.send_string("voltage channel 1 = %s" % voltage_channel1())
                    socket.send_string("voltage channel 2 = %s" % voltage_channel2())   
                    status = get_status()
                    socket.send(runmngr.current_run.run_id)
                    msg = None
                    if status == None:
                        socket.send("Status=None")
                    else:
                        socket.send(status) 
                if get_status() == "FINISHED" and runmngr.current_run.run_id == "stuck_pixel_tuning":
                    add_done_message()
                    break
                    
        if msg == "framerate":
            socket.send("old framerate:%s" % 1/global_vars["integration_time"])
            socket.send("input new framerate:")
            msg = socket.recv()
            try:
                global_vars["integration_time"] = 1 / float(msg)
                socket.send("new framerate:%s" % float(msg))
            except:
                socket.send("invalid input")
                
        if msg == "threshold":
            socket.send("old threshold:%s" % tuning_conf["target_threshold"])
            socket.send("input new threshold:")
            msg = socket.recv()
            try:
                tuning_conf["target_threshold"] = int(msg)
                socket.send("new threshold:%s" % int(msg))
                socket.send("press 'Tune' to tune")          
            except:
                socket.send("invalid input")
                
        if msg =="analyze":
            if global_vars["analyze"]:
                global_vars["analyze"]=False
            else:
                global_vars["analyze"]=True
        
def analyze_beam(beam):
    if len(global_vars["hitrate"]) > 10 and sum(global_vars["hitrate"]) > 10000:                     
        if global_vars["hitrate"][-1] > np.mean(global_vars["hitrate"]) * 0.7:
            global_vars["baseline"].append(global_vars["hitrate"][-1])
            b = np.mean(global_vars["baseline"])
            if beam == False:
                beam = True
                socket.send("beam: on")
            #detect hitrate burst    
            if global_vars["hitrate"][-1] > 2.5 * b:
                socket.send("Time: %s" % datetime.datetime.now().time())  
                socket.send("hitrate peak: %.0f [Hz]" % global_vars["hitrate"][-1])  
        if  global_vars["hitrate"][-1] < np.mean(global_vars["hitrate"]) * 0.2:
            if beam == True:
                beam = False
                socket.send("beam: off")
            #detect moving beamspot
        if beam==True:
            if np.var(global_vars["coloumn"])>10 or np.var(global_vars["row"])>200:
                socket.send("Time: %s" % datetime.datetime.now().time())
                socket.send("Beamspot moved %0.f pixel" % np.sqrt((global_vars["coloumn"][-1]-global_vars["coloumn"][-2])**2+(global_vars["row"][-1]-global_vars["row"][-2])**2))
                socket.send("from %s" % [int( global_vars["coloumn"][-2]),int(global_vars["row"][-2])])
                socket.send("to     %s" % [int(global_vars["coloumn"][-1]),int(global_vars["row"][-1])])
    return beam


# @profile
def analyze(data_array):
    global global_vars
    
    if global_vars["integration_time"] < 0.05:
        global_vars["integration_time"] = 0.05 
    for ro in data_array[0]:
        raw_data = ro[0]
        dr = is_data_record(raw_data)
        global_vars["timestamp_start"].append(ro[1])
        timestamp_stop = ro[2]                            
        global_vars["hits"].append(len(raw_data[dr]))                                              
        if np.any(dr):
            col, row = get_col_row_array_from_data_record_array(raw_data[dr])
             
            global_vars["coloumn"].append(np.mean(col))
            global_vars["row"].append(np.mean(row)) 
                                
            if not np.any(global_vars["hist_occ"]):
                global_vars["hist_occ"] = fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
  
            else:
                global_vars["hist_occ"] += fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
        
        if timestamp_stop - global_vars["timestamp_start"][0] > global_vars["integration_time"]:
            global_vars["hitrate"].append(np.sum(global_vars["hits"]) / (timestamp_stop - global_vars["timestamp_start"][0]))
          #  print ("\nHitrate: %.0f Hz" % global_vars["hitrate"][-1])           
        #      
 #           print "variance coloum: %s" % np.var(global_vars["coloumn"])
 #           print "variance row:    %s" % np.var(global_vars["row"])
            
            if runmngr.current_run.run_id == "fei4_self_trigger_scan" and global_vars["analyze"]:
                global_vars["beam"] = analyze_beam(global_vars["beam"])
            
            
            p_hist = pickle.dumps(global_vars["hist_occ"], -1)
            zlib_hist = zlib.compress(p_hist)              
            socket2.send(zlib_hist)
            # free memory of global variables
            del global_vars["hits"][:]
            del global_vars["coloumn"][:]
            del global_vars["row"][:]
            del global_vars["timestamp_start"][:]
            global_vars["hist_occ"] = None


def handle_data(self, data, new_file=False, flush=True):
    analyze(data)


if __name__ == "__main__":
    main()

