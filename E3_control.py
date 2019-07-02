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
import time
from pybar.fei4_run_base import Fei4RunBase
from pybar.analysis.analyze_raw_data import AnalyzeRawData
from pybar.daq.readout_utils import is_data_record, get_col_row_array_from_data_record_array
from matplotlib import pyplot as plt
import numpy as np
from basil.utils.BitLogic import BitLogic
from pybar_fei4_interpreter import analysis_utils as fast_analysis_utils
from tqdm import tqdm
from pybar_fei4_interpreter.data_interpreter import PyDataInterpreter
from pybar_fei4_interpreter.data_histograming import PyDataHistograming



conf = {
    "Port":5000,
    }

context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://127.0.0.1:%s" % conf["Port"])



# poller = zmq.Poller()
# poller.register(socket, zmq.POLLIN)

#get notified if TTi are not working
try:
    from power_supply import power_off, power_on, voltage_channel1, voltage_channel2
except (SystemExit,):
    raise
except Exception:
    logging.error("Failed to connect to TTi", exc_info=True)
    socket.send("Failed to connect to TTi")
   
runmngr = RunManager("/home/rasmus/git/pyBAR/pybar/configuration.yaml")

run_conf = {"scan_timeout": None,
          "reset_rx_on_error": False}


#global variables
rHit = []
base = []
c=[]
r=[]
hist_occ=None
timestamp=None
readout_index=[]
integration_time = 1

# def daq(word):
#         record_rawdata = int(word)
#         record_word = BitLogic.from_value(value=record_rawdata, size=32)
#         tot2 = record_word[3:0].tovalue()  # find TOT2
#         tot1 = record_word[7:4].tovalue()  # find TOT1
#         if tot1 < 14:
#             row = record_word[16:8].tovalue()
#             coloumn = record_word[23:17].tovalue()
#             x.append(row)
#             y.append(coloumn)
#         if tot2 < 14:
#             row = record_word[16:8].tovalue() + 1
#             coloumn = record_word[23:17].tovalue()
#             x.append(row)
#             y.append(coloumn)
#         else:
#             return 0  
    # print "{0:b}".format(word), FEI4Record(word, chip_flavor="fei4b"), is_data_record(word)
                
#     plt.hist2d(x,y)
#     plt.show()


def get_status():
    if runmngr.current_run:
        return runmngr.current_run.get_run_status()

     
def add_done_message():
    if runmngr.current_run:
        socket.send("Scan finished: %s" % runmngr.current_run.run_id)

        
def main():
    global hist_occ
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
            except (SystemExit,):
                raise
            except Exception:
                logging.error("Failed to initialize", exc_info=True)
                socket.send("Failed to initialize")
            add_done_message()
                
        if get_status() != "RUNNING" and msg == "START":
            # Set own data handle
            #fei4_selftrigger_scan = Fei4SelfTriggerScan()
            Fei4SelfTriggerScan.run_conf = run_conf
            Fei4SelfTriggerScan.handle_data = handle_data
            runmngr.run_run(run=Fei4SelfTriggerScan, run_conf=run_conf, use_thread=True)
            time.sleep(1)
            status = get_status()
            socket.send(status)
            
        if get_status() == "RUNNING" and msg == "STOP":
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
            runmngr.run_run(GdacTuning,use_thread=True)
            while True:
                time.sleep(1)
                try:
                    msg=socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again: 
                    pass
                if get_status() == "FINISHED" and runmngr.current_run.run_id != "tdac_tuning":
                    add_done_message()
                    socket.send("Start TdacTuning")
                    runmngr.run_run(TdacTuning, use_thread=True)   
                if msg == "STOP":
                    runmngr.cancel_current_run(msg)
                    socket.send("%s Run Stopped" % runmngr.current_run.run_id)
                    break  
                if get_status() == "FINISHED" and runmngr.current_run.run_id == "tdac_tuning":
                    add_done_message()
                    break

        if get_status() != "RUNNING" and msg == "sanalog":
            socket.send("Start Analog Scan")
            runmngr.run_run(AnalogScan,use_thread=True)
   
        if get_status() != "RUNNING" and msg == "sdigital":
            socket.send("Start Analog Scan")
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
            socket.send_string("voltage channel 1 = %s" %voltage_channel1())
            socket.send_string("voltage channel 2 = %s" %voltage_channel2())   
            status = get_status()
            socket.send(runmngr.current_run.run_id)
            if status == None:
                socket.send("Status=None")
            else:
                socket.send(status)
    
        if get_status() != "RUNNING" and msg == "fix":
            socket.send("starting Noise Occupancy Tuning (~2min)")
            runmngr.run_run(NoiseOccupancyTuning,use_thread=True)
            while True:
                time.sleep(1)
                try:
                    msg=socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again: 
                    pass
                if get_status() == "FINISHED" and runmngr.current_run.run_id != "stuck_pixel_tuning":
                    add_done_message()
                    socket.send("starting StuckPixelTuning")
                    runmngr.run_run(StuckPixelTuning,use_thread=True)
                if msg == "STOP":
                    runmngr.cancel_current_run(msg)
                    socket.send("%s Run Stopped" % runmngr.current_run.run_id)
                    break
                if get_status() == "FINISHED" and runmngr.current_run.run_id == "stuck_pixel_tuning":
                    add_done_message()
                    break
        
        if msg == "peek":
            start = time.time()
            while True:
                if np.any(hist_occ) != None: 
                    plt.imshow(hist_occ, aspect="auto")
                    plt.ylabel("Row")
                    plt.xlabel("Coloumn")
                    plt.show()
                    break
                if time.time()-start>5:
                    socket.send("Error")
                    break 
                else:
                    time.sleep(0.05)
                    
                    
        
    #    else:
    #        socket.send("invalid input")

def baseline(rHit):
    readout_index.append(0)
    mean=np.mean(rHit)
    return len(readout_index),mean

#@profile
def analyze(data_array):
    from pybar.daq.fei4_record import FEI4Record
 
    
    global rHit         #make rHit global varable?
    global base 
    global c
    global r
    global hist_occ
    global timestamp
    timestamp=[]
#     with tb.open_file(r"/home/rasmus/Documents/Rasmus/10_scc_167_fei4_self_trigger_scan.h5") as in_file:
#         print (in_file.root.meta_data[-1]["timestamp_stop"] - in_file.root.meta_data[0]["timestamp_start"])
#         
#     raise
    
#     interpreter = PyDataInterpreter()
#     interpreter.debug_events(1000, 1011)
#     interpreter.set_FEI4B(False)
#     interpreter.set_trig_count(0)
#     
#     hits_per_event_hist = np.zeros(100)
#     hits_per_event = np.zeros(0)
#     

    #from Replay import Replay   
    #rep = Replay()
    #for i, ro in enumerate(tqdm(rep.get_data(r"/home/rasmus/Documents/Rasmus/110_mimosa_telescope_testbeam_14122016_fei4_self_trigger_scan.h5", real_time=False))):  
    for ro in tqdm(data_array[0]):
        raw_data = ro[0]
        dr = is_data_record(raw_data)
        timestamp.append(ro[1])
#         interpreter.interpret_raw_data(raw_data)    # interpret the raw data
#         hits = interpreter.get_hits()
#         if hits.shape[0] != 0:
#             event_numbers = hits[:]["event_number"].copy()
#             event_numbers -= hits[0]["event_number"]            
#             hist = np.bincount(event_numbers)
#             hits_per_event = np.append(hits_per_event, hist)
#             hits_per_event_hist += np.bincount(hist, minlength=100)
#     plt.bar(range(100), hits_per_event_hist[:100])
#     plt.yscale("log")
#     plt.show()
 
#         print "{0:b}".format(ro[0][0]), FEI4Record(ro[0][0], chip_flavor="fei4b"), is_data_record(ro[0][0])
#  
         
        index,x=baseline(rHit)                                     #x: hitrate, index: Number of Readouts 
        rHit.append(len(raw_data[dr]))
     
        if np.any(dr):
# #             
            col, row = get_col_row_array_from_data_record_array(raw_data[dr])
#        
            if index>500:
                rms = np.sqrt(np.mean([x**2,rHit[-1]**2]))                             
                if rHit[-1]>x*0.75:                                #Hitrate Baseline 
                    base.append(rHit[-1])
                    b=np.mean(base)
                    if rHit[-1]>2.5*b:                               #Hitrate Peak
                        print "\n",len(raw_data[dr])/b
                        print time.time(),"\n"       
                        if  rHit[-1]<np.mean(rHit)*0.25:
                            if rms>20000:
                                print rms
                                print time.time(),"\n"
             
            c.append(np.mean(col))
            r.append(np.mean(row)) 
                                
            if not np.any(hist_occ):
                hist_occ = fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
  
            else:
                hist_occ += fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
              
             
# #         if i > 100000:
# #             break
#     
# 
#     else:
#         interpreter.store_event()     
    return hist_occ,timestamp

def handle_data(self, data):
    import tables as tb
    global timestamp
    global hist_occ
    global rHit
    global integration_time
    
#     if timestamp_start == 0:
#         timestamp_start=data[0][0][1]
      
        
    hist,timestamp=analyze(data)
    
    if timestamp[-1]-timestamp[0]>integration_time: 
        hitrate=np.sum(rHit)/integration_time                        #integration time should be variable
                                                                 
        print ("\nHitrate: %s Hz" % hitrate)           #needs to be fixed from integration time
        socket.send("Hitrate: %s Hz" % hitrate)
        
        print "variance coloum: %s" % np.var(c)
        print "variance row:    %s" % np.var(r)
                
        del rHit[:]
        del c[:]
        del r[:]
        hist_occ=None
        timestamp=None
        
    #send data    
    #socket.send(data)
                                                    
      

#     
    
if __name__ == "__main__":
    
    
    #r,c,hist_occ,rHit = analyze()
    main()
    
#     plt.imshow(hist_occ, aspect="auto")
#     plt.show()
#     
    # Plot Data


#     #Plot Contour Plot of Data
#     fig, ax = plt.subplots()
#     CS = ax.contour(hist_occ)
#     ax.grid(linewidth=0.5)


    # Plot Hitrate of Data



    #plt.plot(hits_per_event)
    #plt.plot(hist_hit)
#     plt.plot(rHit)
#     plt.xlabel("index")
#     plt.ylabel("mean hits per event")
#     plt.text(1500, 30000, "marks 140-230")
#     plt.axvline(140,linewidth=1, color='r')
#     plt.axvline(230,linewidth=1, color='r')
    #plt.axhline(y,linewidth=1, color='r')
#     plt.axis([-80, 2200,np.min(0), np.max(1000)])
              
