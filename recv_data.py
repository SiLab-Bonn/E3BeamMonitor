import sys
import time
from threading import Event, Lock
from optparse import OptionParser

import zmq
import numpy as np
from PyQt5 import Qt
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.dockarea import DockArea, Dock
import pyqtgraph.ptime as ptime

from pybar_fei4_interpreter.data_interpreter import PyDataInterpreter
from pybar_fei4_interpreter.data_histograming import PyDataHistograming
import zlib
import cPickle as pickle


class DataWorker(QtCore.QObject):
    run_start = QtCore.pyqtSignal()
    run_config_data = QtCore.pyqtSignal(dict)
    global_config_data = QtCore.pyqtSignal(dict)
    filename = QtCore.pyqtSignal(dict)
    interpreted_data = QtCore.pyqtSignal(dict)
    meta_data = QtCore.pyqtSignal(dict)
    finished = QtCore.pyqtSignal()
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.integrate_readouts = 1
        self.n_readout = 0
        self._stop_readout = Event()
        self.reset_lock = Lock()

        
    def connect(self, socket_addr):
        self.socket_addr = socket_addr
        self.context = zmq.Context()
        self.socket_pull = self.context.socket(zmq.SUB)  # subscriber
        self.socket_pull.setsockopt(zmq.SUBSCRIBE, '')  # do not filter any data
        self.socket_pull.connect(self.socket_addr)

    
    def process_data(self):
        while(not self._stop_readout.wait(0.01)):  # use wait(), do not block here
            with self.reset_lock:
                data = self.socket_pull.recv()  
                p_hist = zlib.decompress(data)
                data_array = pickle.loads(p_hist)
                if self.integrate_readouts != 0 and self.n_readout % self.integrate_readouts == 0:
                    interpreted_data = {
                        'occupancy': data_array}
                    self.interpreted_data.emit(interpreted_data)
        self.finished.emit()
        
    def stop(self):
        self._stop_readout.set()

        
class OnlineMonitorApplication(QtGui.QMainWindow):

    def __init__(self, socket_addr):
        super(OnlineMonitorApplication, self).__init__()
        self.setup_plots()
        self.add_widgets()
        self.fps = 0  # data frames per second
        self.hps = 0  # hits per second
        self.eps = 0  # events per second
        self.plot_delay = 0
        self.updateTime = ptime.time()
        self.total_hits = 0
        self.total_events = 0
        self.reset_plots()
        self.setup_data_worker_and_start(socket_addr)

    def setup_data_worker_and_start(self, socket_addr):
        self.thread = QtCore.QThread()  # no parent
        self.worker = DataWorker()  # no parent
        self.worker.interpreted_data.connect(self.on_interpreted_data)
        self.worker.run_start.connect(self.on_run_start)
        self.worker.run_config_data.connect(self.on_run_config_data)
    #    self.worker.run_config_data.connect(self.on_run_config_data)
        self.worker.global_config_data.connect(self.on_global_config_data)
        self.worker.moveToThread(self.thread)
        self.worker.connect(socket_addr)
#         self.aboutToQuit.connect(self.worker.stop)  # QtGui.QApplication
        self.thread.started.connect(self.worker.process_data)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        
        
    def setup_plots(self):
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
    
    def add_widgets(self):
        # Main window with dock area
        self.dock_area = DockArea()
        self.setCentralWidget(self.dock_area)
        dock_run_config = Dock("Run configuration", size=(400, 400))
        # Docks
        dock_occcupancy = Dock("Occupancy", size=(400, 400))
        #dock_tti = Dock("tti",size=(400, 400))
        self.dock_area.addDock(dock_occcupancy)
        # Status widget
        cw = QtGui.QWidget()
        cw.setStyleSheet("QWidget {background-color:white}")
        layout = QtGui.QGridLayout()
        cw.setLayout(layout)

        # Run config dock
        self.run_conf_list_widget = Qt.QListWidget()
        dock_run_config.addWidget(self.run_conf_list_widget)

        # Global config dock
        self.global_conf_list_widget = Qt.QListWidget()


        # Different plot docks
        occupancy_graphics = pg.GraphicsLayoutWidget()
        occupancy_graphics.show()
        view = occupancy_graphics.addViewBox()
        self.occupancy_img = pg.ImageItem(border='w')
        view.addItem(self.occupancy_img)
        view.setRange(QtCore.QRectF(0, 0, 80, 336))
        dock_occcupancy.addWidget(occupancy_graphics)
        
    def on_reset(self):
        self.reset_plots()
        self.update_rate(0, 0, 0, 0, 0)
        

    def on_run_start(self):
        # clear config data widgets
        self.run_conf_list_widget.clear()
        self.global_conf_list_widget.clear()
        self.setWindowTitle('Online Monitor')

    def on_run_config_data(self, config_data):
        self.setup_run_config_text(**config_data)

    def on_global_config_data(self, config_data):
        self.setup_global_config_text(**config_data)

    def setup_run_config_text(self, conf):
        for key, value in sorted(conf.iteritems()):
            item = Qt.QListWidgetItem("%s: %s" % (key, value))
            self.run_conf_list_widget.addItem(item)

    def setup_global_config_text(self, conf):
        for key, value in sorted(conf.iteritems()):
            item = Qt.QListWidgetItem("%s: %s" % (key, value))
            self.global_conf_list_widget.addItem(item)

    def setup_filename(self, conf):
        self.setWindowTitle('Online Monitor - %s' % conf)

    def on_interpreted_data(self, interpreted_data):
        self.update_plots(**interpreted_data)

    def reset_plots(self):
        self.update_plots(np.zeros((80, 336, 1), dtype=np.uint8))
    
    def update_plots(self, occupancy):
        self.occupancy_img.setImage(occupancy, autoDownsample=True)
        
    def update_monitor(self):
        now = ptime.time()
        self.plot_delay_label.setText("Plot Delay\n%s" % ((time.strftime('%H:%M:%S', time.gmtime(self.plot_delay))) if abs(self.plot_delay) > 5 else "%1.2f ms" % (self.plot_delay * 1.e3)))
        recent_fps = 1.0 / (now - self.updateTime)  # calculate FPS
        self.updateTime = now
        self.fps = self.fps * 0.7 + recent_fps * 0.3   
            
            
if __name__ == '__main__':
    usage = "Usage: %prog ADDRESS"
    description = "ADDRESS: Remote address of the sender (default: tcp://127.0.0.1:5002)."
    parser = OptionParser(usage, description=description)
    options, args = parser.parse_args()
    if len(args) == 0:
        socket_addr = 'tcp://127.0.0.1:5002'
    elif len(args) == 1:
        socket_addr = args[0]
    else:
        parser.error("incorrect number of arguments")

    app = Qt.QApplication(sys.argv)
#     app.aboutToQuit.connect(myExitHandler)
    win = OnlineMonitorApplication(socket_addr=socket_addr)  # enter remote IP to connect to the other side listening
    win.resize(500, 500)
    win.setWindowTitle('Online Monitor')
    win.show()
    sys.exit(app.exec_())  
