'''Communication with ELSA control system for E3 low current beam monitor'''

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
from pybar.scans.scan_ext_trigger import ExtTriggerScan
import datetime
import time
from pybar.daq.readout_utils import is_data_record, get_col_row_array_from_data_record_array, is_fe_word
import numpy as np
from pybar_fei4_interpreter import analysis_utils as fast_analysis_utils
import zlib
import cPickle as pickle
from pybar.daq import fifo_readout
from pybar.daq import readout_utils as ru

conf = {
    "port_slow_control":5000,
    "port_hit_map":5002,
    }

#global variables
global_vars = {
    "hits":[],
    "baseline":[],
    "coloumn":[],
    "row":[],
    "hist_occ": None,
    "timestamp_start":[],
    "integration_time": 0.05,
    "hitrate":[],
    "beam":True,
    "analyse":True,
    }



run_conf = {"scan_timeout": None,
            "no_data_timeout": None,
            "reset_rx_on_error": False,
            }

run_conf_ext = {"scan_timeout": None,
            "no_data_timeout": None,
            "reset_rx_on_error": False,
            "max_triggers": 0,
            "col_span": [1, 80],  
            "row_span": [1, 336],
            "trigger_delay": 8,
            "trigger_rate_limit": 500,
            "trig_count": 0,
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


def get_status():
    if runmngr.current_run:
        return runmngr.current_run.get_run_status()

     
def add_done_message():
    if runmngr.current_run:
        socket.send("Scan finished: %s" % runmngr.current_run.run_id)

def del_var():
    del global_vars["hits"][:]
    del global_vars["coloumn"][:]
    del global_vars["row"][:]
    del global_vars["timestamp_start"][:]
    del global_vars["hitrate"][:]
    del global_vars["baseline"][:]
    global_vars["hist_occ"] = None
        
        
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
            # status = get_status()
            socket.send("%s" % runmngr.current_run.run_id)
            socket.send(get_status())
            
        if get_status() == "RUNNING" and msg == "STOP":
            fifo_readout.WRITE_INTERVAL = 1
            del_var()
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
            runmngr.run_run(GdacTuning, run_conf=tuning_conf, use_thread=True)
            while True:
                time.sleep(1)
                try:
                    msg = socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again: 
                    pass
                if get_status() == "FINISHED" and runmngr.current_run.run_id != "tdac_tuning":
                    add_done_message()
                    socket.send("Start TdacTuning")
                    runmngr.run_run(TdacTuning, run_conf=tuning_conf, use_thread=True)   
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
            runmngr.run_run(AnalogScan, use_thread=True)
   
        if get_status() != "RUNNING" and msg == "sdigital":
            socket.send("Start Digital Scan")
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
            if status == None:
                socket.send("Status=None")
            else:
                socket.send(runmngr.current_run.run_id)
                socket.send(status)
                if (runmngr.current_run.run_id == "fei4_self_trigger_scan" or runmngr.current_run.run_id == "ext_trigger_scan") and get_status() == "RUNNING":    
                    socket.send("hitrate: %.0f [Hz]" % global_vars["hitrate"][-1])
                    if len(global_vars["coloumn"]) > 0:
                        socket.send("Beamspot: %s pixels" % [int(global_vars["coloumn"][-1]), int(global_vars["row"][-1])])
                
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
            socket.send("old framerate:%1.1f" % float(1/ global_vars["integration_time"]))
            socket.send("input new framerate:")
            msg = socket.recv()
            try:
                global_vars["integration_time"] = 1 / float(msg)
                socket.send("new framerate:%1.1f" % float(1/ global_vars["integration_time"]))
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
                
        if msg == "analyse":
            if global_vars["analyse"]:
                global_vars["analyse"] = False
            else:
                global_vars["analyse"] = True

        if get_status() != "RUNNING" and msg == "ext":
            fifo_readout.WRITE_INTERVAL = 0.05
            ExtTriggerScan.run_conf=run_conf_ext
            ExtTriggerScan.handle_data=handle_data
            runmngr.run_run(run=ExtTriggerScan,run_conf=run_conf_ext, use_thread=True)
            
        
def analyse_beam(beam):
    if len(global_vars["hitrate"]) > 10 and sum(global_vars["hitrate"]) > 10000:                     
        if global_vars["hitrate"][-1] > np.mean(global_vars["hitrate"]) * 0.7:
            global_vars["baseline"].append(global_vars["hitrate"][-1])
            b = np.mean(global_vars["baseline"])
            if beam == False:
                beam = True
                socket.send("beam: on")
            # detect hitrate burst    
            if global_vars["hitrate"][-1] > 2.5 * b:
                socket.send("Time: %s" % datetime.datetime.now().time())  
                socket.send("hitrate peak: %.0f [Hz]" % global_vars["hitrate"][-1])  
        if  global_vars["hitrate"][-1] < np.mean(global_vars["hitrate"]) * 0.2:
            if beam == True:
                beam = False
                socket.send("beam: off")
            # detect moving beamspot
        if beam:
            if np.var(global_vars["coloumn"]) > 100 or np.var(global_vars["row"]) > 500:
                socket.send("Time: %s" % datetime.datetime.now().time())
                socket.send("Beam moved")
#                 socket.send("Beamspot moved %f mm" % np.sqrt(((global_vars["coloumn"][-1] - global_vars["coloumn"][-2])*0.25) ** 2 + ((global_vars["row"][-1] - global_vars["row"][-2])*0.05) ** 2))
#                 socket.send("from %s" % [int(global_vars["coloumn"][-2]), int(global_vars["row"][-2])])
#                 socket.send("to     %s" % [int(global_vars["coloumn"][-1]), int(global_vars["row"][-1])])
                del global_vars["coloumn"][:]
                del global_vars["row"][:]
    return beam


def is_record(value):
    return np.logical_and(is_data_record(value), is_fe_word(value))

#@profile
def analyse(data_array):
    global global_vars
    
    if global_vars["integration_time"] < 0.05:
        global_vars["integration_time"] = 0.05 
    for ro in data_array[0]:
        raw_data = ro[0]
        data_record = ru.convert_data_array(raw_data, filter_func=is_record)   
        global_vars["timestamp_start"].append(ro[1])
        timestamp_stop = ro[2]                            
        global_vars["hits"].append(len(data_record))
                                                      
        if np.any(data_record):
            col, row = get_col_row_array_from_data_record_array(data_record)
             
            global_vars["coloumn"].append(np.mean(col))
            global_vars["row"].append(np.mean(row)) 
                                
            if not np.any(global_vars["hist_occ"]):
                global_vars["hist_occ"] = fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
            else:
                global_vars["hist_occ"] += fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
        
        if timestamp_stop - global_vars["timestamp_start"][0] > global_vars["integration_time"]:
            global_vars["hitrate"].append(np.sum(global_vars["hits"]) / (timestamp_stop - global_vars["timestamp_start"][0]))
            
            if (runmngr.current_run.run_id == "fei4_self_trigger_scan" or runmngr.current_run.run_id == "ext_trigger_scan") and global_vars["analyse"]:
                global_vars["beam"] = analyse_beam(global_vars["beam"])
            
            p_hist = pickle.dumps(global_vars["hist_occ"], -1)
            zlib_hist = zlib.compress(p_hist)              
            socket2.send(zlib_hist)
            # free memory of global variables
            del global_vars["hits"][:]
            del global_vars["timestamp_start"][:]
            global_vars["hist_occ"] = None
        

def handle_data(self, data, new_file=False, flush=True):
    analyse(data)
    

if __name__ == "__main__":
    main()

