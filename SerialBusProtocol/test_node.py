import random
# import inspect



class DataGenerator:
    
    def __init__(self, writer, reader):
        self.writer = writer
        self.reader = reader
        self.sent_frames = []
        self.received_frames = []
        
    def generate_frame(self, num_bytes):
        frame = int(random.randint(0,255)).to_bytes(num_bytes, byteorder='little')
        self.sent_frames.append(frame)
        return frame
    
    def record_rx_frame(self, frame):
        self.received_frames.append(frame)
        
    def check_all_frames_successfully_received(self):
        assert len(self.sent_frames) == len(self.received_frames)
        for i in range(len(self.received_frames)):
            assert self.sent_frames[i] == self.received_frames[i]


class Clock:
    
    def __init__(self, id, ticks, ticks_per_sec):
        self.id = id
        self.ticks = ticks
        self.ticks_per_sec = ticks_per_sec
    
    def time(self):
        return self.ticks / self.ticks_per_sec
        
    def incr_ticks(self, ticks):
        self.ticks += ticks
    
    def set_time(self, time):
        self.ticks = int(self.ticks_per_sec * time)
        

# Just record tx data in a buffer to be handled by the TestWire
class TestTxWriter:
    
    def __init__(self):
        self.buffer = []
        
    def write(self, data):
        self.buffer += data


# The TestWire will add data to the buffer. Read back full frames  - TODO
class TestRxReader:
    
    def __init__(self):
        self.buffer = []
    
    # read back if a full frame is ready (use None to delimit frames)
    def read(self):
        if len(self.buffer) == 0:
            return []
        while self.buffer[0] == None:
            self.buffer.pop(0)
            if len(self.buffer) == 0:
                return []
        if None in self.buffer:
            end = self.buffer.index(None)
            read_data = self.buffer[:end]
            del self.buffer[:end]
            return read_data
        else:
            # print("Read nothing")
            return []

   
# A node just wraps a reader, writer, clock and protocol
class Node:
    def __init__(self, tx_writer, rx_reader, clock, protocol):
        self.clock = clock
        self.tx_writer = tx_writer
        self.rx_reader = rx_reader
        self.protocol = protocol
    
    def process_rx(self):
        self.protocol.process_rx()
        
    def process_tx(self):
        self.protocol.process_tx()
        
    def update_clock(self, ticks):
        self.clock.incr_ticks(ticks)


# The TestWire is trying to simulate a shared wire/link/bus between multiple nodes
# In particular to flag any corruption arising from multiple nodes transmitting at once
class TestWire: # TODO: rename bus
    
    def __init__(self):
        self.nodes = []
    
    def add_node(self, node):
        self.nodes.append(node)
    
    # To be called every time a byte is to be sent over the bus
    def update(self, corrupt_byte=False, additional_byte=False, lost_byte=False):
        # Shift the data out from all the tx buffers
        data = None
        for node in self.nodes:
            tx_buffer = node.tx_writer.buffer
            if len(tx_buffer) > 0:
                if data == None:
                    data = tx_buffer[0]
                else:
                    # Corrupted data - could do something else, like "corrupted" or XOR(self.tx_buffers)
                    data = random.randint(0, 0xFF) 
                tx_buffer.pop(0)
        
        if corrupt_byte:
            data = random.randint(0, 0xFF)
        elif additional_byte:
            data = [data, random.randint(0, 0xFF)]
        elif lost_byte:
            data = None
        
        for node in self.nodes:
            node.rx_reader.buffer += [data]



