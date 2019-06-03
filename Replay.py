''' This is a producer faking data coming from bdaq53

    Real data is send in chunks with correct timing.
    This producer is needed for debugging and testing.
'''

import time

import tables as tb


class Replay(object):

    def __init__(self):
        self.delay = 0.

    def get_data(self, data_file):
        self.data_file = data_file
        for data in self._get_data():
            time.sleep(self.delay)
            yield data

    def _get_data(self):
        ''' Yield data of one readout

            Delay return if replay is too fast
        '''
        with tb.open_file(self.data_file, mode="r") as in_file_h5:
            meta_data = in_file_h5.root.meta_data[:]
            raw_data = in_file_h5.root.raw_data
            n_readouts = meta_data.shape[0]

            self.last_readout_time = time.time()

            for i in range(n_readouts):
                # Raw data indeces of readout
                i_start = meta_data['index_start'][i]
                i_stop = meta_data['index_stop'][i]

                # Time stamps of readout
                t_stop = meta_data[i]['timestamp_stop']
                t_start = meta_data[i]['timestamp_start']

                # Create data of readout (raw data + meta data)
                data = []
                data.append(raw_data[i_start:i_stop])
                data.extend((float(t_start),
                             float(t_stop),
                             int(meta_data[i]['error'])))

                # Determine replay delays
                if i == 0:  # Initialize on first readout
                    self.last_timestamp_start = t_start
                now = time.time()
                delay = now - self.last_readout_time
                additional_delay = t_start - self.last_timestamp_start - delay
                if additional_delay > 0:
                    # Wait if send too fast, especially needed when readout was
                    # stopped during data taking (e.g. for mask shifting)
                    time.sleep(additional_delay)
                self.last_readout_time = time.time()
                self.last_timestamp_start = t_start

                yield data

    def __del__(self):
        self.in_file_h5.close()
        
if __name__ == "__main__":
    rep = Replay()
    for ro in rep.get_data(r"/home/rasmus/git/pyBAR/pybar/data2/module_0/6_module_0_noise_occupancy_tuning.h5"):
        print ro
