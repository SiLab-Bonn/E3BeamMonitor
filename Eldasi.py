''' ELSA DAQ Sim: Simulate the ELSA DAQ ZMQ protocoll for testing '''
import sys
import zmq

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtWidgets import QPlainTextEdit, QPushButton, QLineEdit
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout
from PyQt5.QtCore import QSocketNotifier


class Server():
    def start(self, address):
        self.context = zmq.Context.instance()
        server = self.context.socket(zmq.PAIR)
        server.setsockopt(zmq.IDENTITY, b'ELSA DAQ')
        try:
            server.bind(address)
        except zmq.error.ZMQError as e:
            return e.strerror

        self.socket = server
        return True

    def dispatch(self, msg):
        self.socket.send_string(msg)

    def recv(self):
        return self.socket.recv_multipart()


class Eldasi(QWidget):

    def __init__(self):
        super(Eldasi, self).__init__()
        self.initUI()
        self.client_available = False

    def initUI(self):
        # widgets to enable/disable depending on connection status
        self.toggle_widgets = []

        # Log widget
        self.log_text = QPlainTextEdit(self)

        # Quick connections layout
        connections_layout = QHBoxLayout()
        self.address_text = QLineEdit(self, text='tcp://127.0.0.1:5000')
        self.connect_button = QPushButton("Start server")
        connections_layout.addWidget(self.address_text)
        connections_layout.addWidget(self.connect_button)
        self.connect_button.clicked.connect(self.start_server)

        # Text send widgets
        send_button = QPushButton("Send")
        send_button.clicked.connect(lambda: self._send_data(self.data_text.text()))
        self.data_text = QLineEdit(self)
        send_layout = QHBoxLayout()
        send_layout.addWidget(send_button)
        send_layout.addWidget(self.data_text)
        self.toggle_widgets.extend([send_button, self.data_text])

        # Quick ELSA commands widgets
        commands_layout = QHBoxLayout()
        start_button = QPushButton("Start")
        start_button.clicked.connect(lambda: self._send_data("START"))
        commands_layout.addWidget(start_button)
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(lambda: self._send_data("STOP"))
        commands_layout.addWidget(stop_button)
        tune_button = QPushButton("Tune")
        tune_button.clicked.connect(lambda: self._send_data("TUNE"))
        commands_layout.addWidget(tune_button)
        self.toggle_widgets.extend([start_button, stop_button, tune_button])

        # Combine widgets to layout
        layout = QGridLayout()
        layout.addWidget(self.log_text, 1, 1)
        layout.addLayout(connections_layout, 2, 1)
        layout.addLayout(commands_layout, 3, 1)
        layout.addLayout(send_layout, 4, 1)
        self.setLayout(layout)

        # Window settings
        self.setGeometry(200, 200, 480, 400)
        self.setWindowTitle('ELSA DAQ Simulation')
        self.show()

        self._switch_widgets()

        self._log('[UI] started')

    def start_server(self):
        self._server = Server()
        ret = self._server.start(self.address_text.text())
        if ret is not True:
            self._log("[ZMQError]: " + repr(ret))
            return
        socket = self._server.socket
        self._notifier = QSocketNotifier(socket.getsockopt(zmq.FD),
                                         QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._socket_activity)
        self._notifier.setEnabled(True)
        self.connect_button.clicked.disconnect()
        self.connect_button.clicked.connect(self.stop_server)
        self.connect_button.setText('Stop server')
        self._log("[Socket] Start server")

    def stop_server(self):
        self._notifier.setEnabled(False)
        self._server.socket.close()
        self._notifier.activated.disconnect()
        self._switch_widgets(False)
        self.connect_button.clicked.disconnect()
        self.connect_button.clicked.connect(self.start_server)
        self.connect_button.setText('Start server')
        self._log("[Socket] Stop server")

    def _switch_widgets(self, status=None):
        if status is None:
            self._switch_widgets(status=not self.toggle_widgets[0].isEnabled())
        else:
            for w in self.toggle_widgets:
                w.setEnabled(status)

    def _log(self, data):
        self.log_text.appendPlainText(data)

    def _send_data(self, data):
        if data:
            self._server.dispatch(data)
            self._log("[UI] sent: " + data)

    def _socket_activity(self):
        self._notifier.setEnabled(False)
        socket = self._server.socket
        if socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            while socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
                received = self._server.recv()
                self._log("[Socket] received: " + repr(received))
        # Called when client connects
        elif socket.getsockopt(zmq.EVENTS) & zmq.POLLOUT:
            self._log("[Socket] Client connected")
            self.client_available = True
            self._switch_widgets(True)
        else:
            self.client_available = False
            self._switch_widgets(False)
        self._notifier.setEnabled(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = Eldasi()
    sys.exit(app.exec_())
