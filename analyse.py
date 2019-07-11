''' Replay program to analyze data and test analysing setups. '''
import zmq
import datetime
from pybar.daq.readout_utils import is_data_record, get_col_row_array_from_data_record_array
from matplotlib import pyplot as plt
import numpy as np
from pybar_fei4_interpreter import analysis_utils as fast_analysis_utils
from tqdm import tqdm
import zlib
import cPickle as pickle
from Replay import Replay  

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
    "integration_time": 0.05,
    "hitrate":[],
    "beam":True,
    "time":[],
    "c":[],
    "r":[],
    "analyze":True
    }


context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://127.0.0.1:%s" % conf["port_slow_control"])

context2 = zmq.Context()
socket2 = context2.socket(zmq.PUB)
socket2.bind("tcp://127.0.0.1:%s" % conf["port_hit_map"])

# @profile
def analyze():
    global global_vars
    
    if global_vars["integration_time"] < 0.05:
        global_vars["integration_time"] = 0.05

 
    rep = Replay() 
    for i, ro in enumerate(tqdm(rep.get_data(r"/home/rasmus/Documents/Rasmus/am_241_p_threshold54_moving.h5", real_time=True))):  
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
            #    global_vars["hist_occ"] = fast_analysis_utils.hist_2d_index(np.mean(col), np.mean(row), shape=(81, 337))
            else:
                global_vars["hist_occ"] += fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
            #    global_vars["hist_occ"] += fast_analysis_utils.hist_2d_index(np.mean(col), np.mean(row), shape=(81, 337))
        if len(global_vars["time"])==0:
            global_vars["time"].append(0)
        

        if timestamp_stop - global_vars["timestamp_start"][0] > global_vars["integration_time"]:
            
            
            #print ("\nHitrate: %.0f Hz" % global_vars["hitrate"][-1])           
#           global_vars["start_time"]=time.time()
            global_vars["time"].append(global_vars["time"][-1]+timestamp_stop-global_vars["timestamp_start"][0])
        #      
        
#             print "\nmean coloum: %s" % np.mean(global_vars["coloumn"])
#             print "mean row:    %s" % np.mean(global_vars["row"])
#             print "variance coloum: %s" % np.var(global_vars["coloumn"])
#             print "variance row:    %s" % np.var(global_vars["row"])
        
            global_vars["c"].append(np.mean(global_vars["coloumn"]))
            global_vars["r"].append(np.mean(global_vars["row"]))


                

            global_vars["hitrate"].append(np.sum(global_vars["hits"]) / (timestamp_stop - global_vars["timestamp_start"][0]))
            if global_vars["analyze"]:
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
            

def analyze_beam(beam):
    if len(global_vars["hitrate"]) > 10 and sum(global_vars["hitrate"]) > 10000:                     
        if global_vars["hitrate"][-1] > np.mean(global_vars["hitrate"]) * 0.7:
            global_vars["baseline"].append(global_vars["hitrate"][-1])
            b = np.mean(global_vars["baseline"])
            if beam == False:
                beam = True
                socket.send("beam: on")
            if global_vars["hitrate"][-1] > 2.5 * b:  # Hitrate Peak               
                socket.send("hitrate peak: %.0f [Hz]" % global_vars["hitrate"][-1])      
        if  global_vars["hitrate"][-1] < np.mean(global_vars["hitrate"]) * 0.2:
            if beam == True:
                beam = False
                socket.send("beam: off")
        if beam==True:
            if np.var(global_vars["coloumn"])>10 or np.var(global_vars["row"])>200:
                socket.send("Beamspot moved %0.f pixel" % np.sqrt((global_vars["coloumn"][-1]-global_vars["coloumn"][-2])**2+(global_vars["row"][-1]-global_vars["row"][-2])**2))
                socket.send("from %s" % [int( global_vars["coloumn"][-2]),int(global_vars["row"][-2])])
                socket.send("to     %s" % [int(global_vars["coloumn"][-1]),int(global_vars["row"][-1])])
    return beam




if __name__ == "__main__":
    

    analyze()

#     
    # Plot Data
#     global_vars["time"].remove(0)
#     plt.subplot(2,1,1)
#     plt.plot(global_vars["time"],global_vars["hitrate"])
#     plt.xlabel("Time [s]")
#     plt.ylabel("Hitrate [Hz]")
#     plt.subplot(2,1,2)
#     plt.hist(global_vars["hitrate"],bins=1000)
#     plt.xlabel("hitrate [Hz]")
#     plt.ylabel("occurence")  


#     global_vars["time"].remove(0)
#     plt.subplot(2,1,1)
#     plt.plot(global_vars["time"],global_vars["c"])
#     plt.xlabel("Time [s]")
#     plt.ylabel("coloumn")
#     plt.subplot(2,1,2)
#     plt.plot(global_vars["time"],global_vars["r"])
#     plt.xlabel("Time [s]")
#     plt.ylabel("row")  




    # Plot Contour Plot of Data
    fig, ax = plt.subplots()
    CS = ax.contour(global_vars["hist_occ"])
    ax.grid(linewidth=0.5)
    plt.xlabel("coloumn")
    plt.ylabel("row")
    #plt.colorbar(CS)
 
    plt.imshow(global_vars["hist_occ"], aspect="auto")
    plt.xlabel("coloumn")
    plt.ylabel("row")
    plt.colorbar()
    
    # plt.plot(hits_per_event)
    # plt.plot(hist_hit)
#     plt.plot(rHit)
#     plt.xlabel("index")
#     plt.ylabel("mean hits per event")
#     plt.text(1500, 30000, "marks 140-230")
#     plt.axvline(140,linewidth=1, color='r')
#     plt.axvline(230,linewidth=1, color='r')
    # plt.axhline(y,linewidth=1, color='r')
#     plt.axis([-80, 2200,np.min(0), np.max(1000)])

    plt.show()