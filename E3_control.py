''' Communication with ELSA control system for E3 low current beam monitor'''

import zmq
import logging
from basil.dut import Dut
from pyBAR.pybar.fei4_run_base import Fei4RunBase
from pyBAR.pybar.run_manager import RunManager
from pyBAR.pybar.scans.tune_gdac import GdacTuning
from pybar.scans.tune_tdac import TdacTuning
from pybar.scans.scan_threshold import ThresholdScan
from pybar.scans.scan_analog import AnalogScan
from pybar.scans.scan_digital import DigitalScan
import json
from pybar.scans.tune_noise_occupancy import NoiseOccupancyTuning
from pybar.scans.tune_stuck_pixel import StuckPixelTuning
from pybar.scans.scan_fei4_self_trigger import Fei4SelfTriggerScan
import time
from pybar.analysis.analyze_raw_data import AnalyzeRawData
from pybar.daq.readout_utils import build_events_from_raw_data, is_trigger_word, get_trigger_data, is_data_record
from matplotlib import pyplot as plt


conf = {
    "Port":5000,
    }

context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://127.0.0.1:%s" % conf["Port"])

#poller = zmq.Poller()
#poller.register(socket, zmq.POLLIN)

try:
    from pybar.scans.power_supply import power_off, power_on, voltage_channel1, voltage_channel2
#     if RuntimeError:      #Error if the program starts before TTi initialized 
#         socket.send("Failed to connect to TTi")
except (SystemExit, ):
    raise
except Exception:
    logging.error("Failed to connect to TTi", exc_info=True)
    socket.send("Failed to connect to TTi")



   
runmngr = RunManager("configuration.yaml")

run_conf = {"scan_timeout": None,
          "reset_rx_on_error": False}

def handle_data(cls, data, new_file=False, flush=True):
    
    
    
    
#     with AnalyzeRawData(create_pdf=False) as analyze_raw_data:
#         analyze_raw_data.create_source_scan_hist = True
#         analyze_raw_data.plot_histograms()
    print data
    
    

def get_status():
    if runmngr.current_run:
        return runmngr.current_run.get_run_status()
     
def add_done_message():
    if runmngr.current_run:
        socket.send("Scan finished: %s" % runmngr.current_run.run_id)
        
def main():
    while True:  # should alwayz run no blocking
        # poller.poll(100)  # wait up to 100 ms
        msg = socket.recv()
        
        if get_status() != "RUNNING" and msg == "init":
            try:
                socket.send("start initializing")
                power_on()
                socket.send_string("voltage channel 1 = %s " % voltage_channel1())
                socket.send_string("voltage channel 2 = %s " % voltage_channel2())
                runmngr.run_run(run=DigitalScan,)
                #socket.send("Initializing finished")
            except (SystemExit, ):
                raise
            except Exception,e:
                logging.error("Failed to initialize", exc_info=True)
                socket.send("Failed to initialize")
            add_done_message()
            
    
            
        
        if get_status() != "RUNNING" and msg == "START":
            
            
            # Set own data handle
            #fei4_selftrigger_scan = Fei4SelfTriggerScan()
            Fei4SelfTriggerScan.run_conf=run_conf
            Fei4SelfTriggerScan.handle_data = handle_data
            runmngr.run_run(run=Fei4SelfTriggerScan, run_conf=run_conf, use_thread=True)
            
            time.sleep(1)
            status=get_status()
            socket.send(status)
            #runmngr.current_run.connect_cancel([add_done_message])
            
            
            
        if get_status() == "RUNNING" and msg == "STOP":
            runmngr.cancel_current_run(msg)
            socket.send("Current Run Stopped")
            
    
        if msg == "exit":
            if runmngr:
                runmngr.close()
                break
            logging.info("Program terminates")
            socket.send("Program terminates")
         
        if get_status() != "RUNNING" and msg == "TUNE":
            socket.send("Start GdacTuning")
            runmngr.run_run(GdacTuning,)
            add_done_message()
            socket.send("Start TdacTuning")
            runmngr.run_run(TdacTuning,)
            add_done_message()
    
            
        if msg == "sanalog":
            socket.send("Start Analog Scan")
            runmngr.run_run(AnalogScan)
            add_done_message()
            
        if msg == "sdigital":
            socket.send("Start Analog Scan")
            runmngr.run_run(DigitalScan)
            add_done_message()
            
        if msg == "poweron":
            power_on()
            socket.send_string("voltage channel 1 = %s " % voltage_channel1())
            socket.send_string("voltage channel 2 = %s " % voltage_channel2()) 
             
        if msg == "poweroff":
            power_off()
            socket.send_string("voltage channel 1 = %s " % voltage_channel1())
            socket.send_string("voltage channel 2 = %s " % voltage_channel2()) 
    
        if msg == "status":
            # socket.send_string("voltage channel 1 = %s" %voltage_channel1())
            #socket.send_string("voltage channel 2 = %s" %voltage_channel2())   
            #join = runmngr.run_run(run=AnalogScan, run_conf={"scan_parameters": [('PlsrDAC', 280)], "n_injections": 200}, use_thread=True)  
            #status = join()
            #print 'Status:', status
            # status=json.dumps(run_status)
            # logging.info("%s" % status)
            status=get_status()
            if status==None:
                socket.send("Status=None")
            else:
                socket.send(status)
    
        if msg == "fix":
            socket.send("starting Noise Occupancy Tuning")
            runmngr.run_run(NoiseOccupancyTuning)
            add_done_message()
            socket.send("starting Stuck Pixel Tuning")
            runmngr.run_run(StuckPixelTuning)
            add_done_message()
        
        

    #    else:
    #        socket.send("invalid input")



    
if __name__ == "__main__":
    main()
    import tables as tb
    from pybar.daq.fei4_record import FEI4Record
     
    #rep = Replay()
    for ro in rep.get_data(r"/home/rasmus/git/pyBAR/pybar/data2/module_0/6_module_0_noise_occupancy_tuning.h5"):
 
        with tb.open_file(r"/home/rasmus/git/pyBAR/pybar/data2/module_0/6_module_0_noise_occupancy_tuning.h5") as in_file:
            for word in in_file.root.raw_data:
                print "{0:b}".format(word), FEI4Record(word, chip_flavor="fei4b"), is_data_record(word)


