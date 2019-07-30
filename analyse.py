''' Replay program to analyze data and test analysing setups. '''
import zmq
from pybar.daq.readout_utils import is_data_record, get_col_row_array_from_data_record_array, is_fe_word
from pybar.daq import readout_utils as ru
from matplotlib import pyplot as plt
import numpy as np
from pybar_fei4_interpreter import analysis_utils as fast_analysis_utils
from tqdm import tqdm
import zlib
import cPickle as pickle
from Replay import Replay  
from basil.utils.BitLogic import BitLogic
from pybar_fei4_interpreter.data_interpreter import PyDataInterpreter
from pybar_fei4_interpreter.data_histograming import PyDataHistograming

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
    "analyse":True,
    "beamspot":[],
    "tot":[]
    }

context = zmq.Context()
socket = context.socket(zmq.PAIR)
socket.connect("tcp://127.0.0.1:%s" % conf["port_slow_control"])

context2 = zmq.Context()
socket2 = context2.socket(zmq.PUB)
socket2.bind("tcp://127.0.0.1:%s" % conf["port_hit_map"])

def is_record(value):
    return np.logical_and(is_data_record(value), is_fe_word(value))


#@profile
def analyse():
    global global_vars
    
#     if global_vars["integration_time"] < 0.05:
#         global_vars["integration_time"] = 0.05


 
    rep = Replay() 
    for i, ro in enumerate(tqdm(rep.get_data(r"/home/rasmus/Documents/Rasmus/moving_beam/24_module_0_fei4_self_trigger_scan.h5", real_time=False))):
    
        raw_data = ro[0]
        
        data_record = ru.convert_data_array(raw_data, filter_func=is_record)
#         if np.any(is_trigger_word(data_record)):
#             raise
        
        #dr = is_data_record(raw_data)
 
        global_vars["timestamp_start"].append(ro[1])
        timestamp_stop = ro[2]
        global_vars["hits"].append(len(data_record))
         
#        print "{0:b}".format(ro[0][0]), FEI4Record(ro[0][0], chip_flavor="fei4b"), is_data_record(ro[0][0])
        
        if np.any(data_record):
            col, row = get_col_row_array_from_data_record_array(data_record)
            global_vars["coloumn"].append(np.median(col))
            global_vars["row"].append(np.median(row))               
            if not np.any(global_vars["hist_occ"]):
                global_vars["hist_occ"] = fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
            #    global_vars["hist_occ"] = fast_analysis_utils.hist_2d_index(np.mean(col), np.mean(row), shape=(81, 337))
            else:
                global_vars["hist_occ"] += fast_analysis_utils.hist_2d_index(col, row, shape=(81, 337))
            #   global_vars["hist_occ"] += fast_analysis_utils.hist_2d_index(np.mean(col), np.mean(row), shape=(81, 337))
             
            if len(global_vars["time"]) == 0:
                global_vars["time"].append(0)

            if timestamp_stop - global_vars["timestamp_start"][0] > global_vars["integration_time"]:
                global_vars["time"].append(global_vars["time"][-1] + timestamp_stop - global_vars["timestamp_start"][0])
                global_vars["c"].append(np.var(global_vars["coloumn"]))
                global_vars["r"].append(np.var(global_vars["row"]))
                global_vars["hitrate"].append(np.sum(global_vars["hits"]) / (timestamp_stop - global_vars["timestamp_start"][0]))
                if global_vars["analyse"]:
                    global_vars["beam"] = analyse_beam(global_vars["beam"])
                 
                p_hist = pickle.dumps(global_vars["hist_occ"], -1)
                zlib_hist = zlib.compress(p_hist)
                socket2.send(zlib_hist)
    #             # free memory of global variables
                del global_vars["hits"][:]
                del global_vars["timestamp_start"][:]
                global_vars["hist_occ"] = None
                if len(global_vars["coloumn"])>100:
                    del global_vars["coloumn"][:]
                    del global_vars["row"][:]

def analyse_beam(beam):
    if len(global_vars["hitrate"]) > 10 and sum(global_vars["hitrate"]) > 10000:
        if global_vars["hitrate"][-1] > np.median(global_vars["hitrate"]) * 0.7:
            global_vars["baseline"].append(np.median(global_vars["hitrate"]))
            b = np.mean(global_vars["baseline"])
            if beam == False:
                beam = True
                socket.send("beam: on")
            if global_vars["hitrate"][-1] > 2.5 * b:  # Hitrate Peak               
                socket.send("hitrate peak: %.0f [Hz]" % global_vars["hitrate"][-1])      
        if  global_vars["hitrate"][-1] < np.median(global_vars["hitrate"]) * 0.2:
            if beam == True:
                beam = False
                socket.send("beam: off")
        if beam:
            global_vars["beamspot"].append(np.sqrt(((global_vars["coloumn"][-1] - np.median(global_vars["coloumn"]))*0.25) ** 2 + ((global_vars["row"][-1] - np.median(global_vars["row"]))*0.05) ** 2))
    
            if np.var(global_vars["coloumn"]) > 100 or np.var(global_vars["row"]) > 500:
                try:
                    socket.send("Beamspot moved %0.2f mm" % np.sqrt(((global_vars["coloumn"][-1] - np.median(global_vars["coloumn"]))*0.250) ** 2 + ((global_vars["row"][-1] - np.median(global_vars["row"]))*0.050) ** 2))
                    socket.send("Time: %s" % global_vars["time"][-1])
                    del global_vars["coloumn"][:]
                    del global_vars["row"][:]
                except:
                    pass
#                 socket.send("from %s" % [int(global_vars["coloumn"][-2]), int(global_vars["row"][-2])])
#                 socket.send("to     %s" % [int(global_vars["coloumn"][-1]), int(global_vars["row"][-1])])

    return beam


if __name__ == "__main__":

    analyse()

    # Plot Data
    global_vars["time"].remove(0)
#     plt.subplot(3,1,1)
#     plt.plot(global_vars["time"],global_vars["hitrate"])
#     plt.xlabel("Time [s]")
#     plt.ylabel("Hitrate [Hz]")
#     plt.hlines(np.mean(global_vars["baseline"]),xmin=0,xmax=40, colors='k', linestyles='solid', label='baseline')
#     plt.hlines(np.mean(global_vars["baseline"])*0.7,xmin=0,xmax=40, colors='r', linestyles='solid', label='baseline')
#     plt.hlines(np.mean(global_vars["baseline"])*0.2,xmin=0,xmax=40, colors='g', linestyles='solid', label='baseline')
#     plt.title("baselines")
#     plt.subplot(2,1,1)
#     plt.plot(global_vars["time"],global_vars["c"])
#     plt.ylabel("var coloumn")
#     plt.xlabel("Time [s]")
#     plt.subplot(2,1,2)
#     plt.plot(global_vars["time"],global_vars["r"])
#     plt.ylabel("var row")
#     plt.xlabel("Time [s]")
      
#     plt.subplot(5,1,3)
#     plt.plot(global_vars["time"], global_vars["beamspot"])
#     plt.xlabel("Time [s]")
#     plt.ylabel("beamspot moving [pixel")   
#     plt.hist(global_vars["beamspot"],bins=100)
#     plt.xlabel("beamspot moving [mm]")
#     plt.ylabel("occurence")  

    # Plot Contour Plot of Data
#     fig, ax = plt.subplots()
#     CS = ax.contour(global_vars["hist_occ"])
#     ax.grid(linewidth=0.5)
#     plt.xlabel("coloumn")
#     plt.ylabel("row")
#     #plt.colorbar(CS)
#    
#     plt.imshow(global_vars["hist_occ"], aspect="auto")
#     plt.xlabel("coloumn")
#     plt.ylabel("row")
#     plt.colorbar()
#     plt.title("Hit Occurence")

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
