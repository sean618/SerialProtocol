import random
# import uuid as uuid
import time
import inspect

# TODO: make more settings configurable
NUM_UUID_BYTES = 1

class DataGenerator:
    
    def __init__(self, writer, reader):
        self.writer = writer
        self.reader = reader
    
    def process_tx(self, max_tx_packet_bytes):
        frame = int(random.randint(0,255)).to_bytes(max_tx_packet_bytes, byteorder='little')
        
    def process_rx(self):
        
        
        

# TODO: support nodes having different integer multiples of the time slot.
#       This could be done as an initialisation stage where every node sends,
#       in turn, a list of all known slot multiples including it's own.
class TimeDivisionMultiplexingProtocol:
    
    SYNC_PACKET_TYPE = 0xAA
    
    def __init__(self, clock, node_id, num_nodes, time_per_node, time_between_sync_packets, time_for_tx_to_reach_rx, time_margin):
        self.time_between_sync_packets = time_between_sync_packets
        self.clock = clock
        self.time_for_tx_to_reach_rx = time_for_tx_to_reach_rx
        self.num_nodes = num_nodes
        self.node_id = node_id
        self.time_per_node = time_per_node
        self.cycle_period = num_nodes * time_per_node
        self.start_tx_time = node_id * time_per_node
        self.end_tx_time = (node_id + 1) * time_per_node - time_margin
        self.next_sync_time = 0
        
    def __tx_sync_packet(self):
        frame = int(self.SYNC_PACKET_TYPE).to_bytes(1, byteorder='little')
        # Convert time into pico seconds and pack it into 16 bytes
        frame = int(self.clock.time() * 1000*1000*1000*1000).to_bytes(10, byteorder='little')
        self.tx_writer.write(frame)
        
    def __handle_rx_sync_packet(self, bytes):
        sent_time = int.from_bytes(bytes, byteorder='little') / (1000*1000*1000*1000)
        expected_time_now = sent_time + self.time_for_tx_to_reach_rx
        # Move the clock to between the expected time and our current time
        new_time = self.clock.time() + (expected_time_now - self.clock.time())/2 
        self.clock.set_time(expected_time_now)
    
    def process_tx(self):
        now = self.clock.time()
        if now > self.start_tx_time and now < self.end_tx_time:
            if now > self.next_sync_time:
                self.__tx_sync_packet()
                self.next_sync_time = now + self.time_between_sync_packets
            else:
                pass
    
    def process_rx(self, bytes):
        if bytes[0] == self.SYNC_PACKET_TYPE:
            self.__handle_sync_packet()


class EnumerationProtocol:
    
    UNENUMERATED_NODE_ID = 0xFF
    
    # max_time_between_enum_frames: controls the frequency of enum frames
    # This whole protocol relies on the multiple nodes not transmitting at the same time
    # so we need this number to be large enough that it's fairly rare that multiple nodes
    # will send an enum frame whilst another is sending their's
    # (The larger it is the longer the enumeration step takes though)
    def __init__(self, tx_writer, rx_reader, clock, uuid, max_time_between_enum_frames):
        self.num_times_started = 0
        self.rx_reader = rx_reader
        self.tx_writer = tx_writer
        self.clock = clock
        self.uuid = uuid
        self.max_time_between_enum_frames = max_time_between_enum_frames
        self.FINISHED_WAIT_TIME = 4 * max_time_between_enum_frames
        self.reset_state()
    
    def reset_state(self):
        # print("Resetting Enum protocol")
        self.num_times_started += 1
        self.__next_tx_frame_time = 0.0
        self.finished_time = 0.0
        self.sorted_uuids = [self.uuid]
        self.receivedOwnUuid = False
        self.finished = False
        self.id = self.UNENUMERATED_NODE_ID
    
    def __tx_enum_frame(self):
        # print("Time:", self.clock.time(), "Tx enum frame, UUID:", self.uuid)
        frame = int(self.UNENUMERATED_NODE_ID).to_bytes(1, byteorder='little')
        for uuid in self.sorted_uuids:
            frame = frame + int(uuid).to_bytes(NUM_UUID_BYTES, byteorder='little')
        self.tx_writer.write(frame)
    
    def __rx_handle_enum_frame(self, bytes):
        # print("Time:", self.clock.time(), "Rx enum frame, UUID:", self.uuid)
        # Read all the uuids
        for n in range(int(len(bytes) / NUM_UUID_BYTES)):
            uuid = int.from_bytes(bytes[n*NUM_UUID_BYTES:n*NUM_UUID_BYTES+1], byteorder='little')
            # Add any new UUIDs to the list
            if uuid not in self.sorted_uuids:
                self.sorted_uuids.append(uuid)
                # Every time there is a new uuid update the time to wait before finished
                self.finished_time = self.clock.time() + self.FINISHED_WAIT_TIME
            # Record if we seen our UUID
            if uuid == self.uuid:
                self.receivedOwnUuid = True
        self.sorted_uuids.sort()
    
    def process_tx(self):
        if not self.finished:
            if self.clock.time() > self.__next_tx_frame_time:
                self.__next_tx_frame_time = self.clock.time() + (self.max_time_between_enum_frames * random.random())
                # Transmit our list of uuids if we are the lowest uuid in the list (therefore the Master)
                # Or if we haven't received our own uuid yet
                if self.uuid == self.sorted_uuids[0] or not self.receivedOwnUuid:
                    self.__tx_enum_frame()    
    
    def process_rx(self):
        bytes = self.rx_reader.read()
        if len(bytes) > 0:
            if bytes[0] == self.UNENUMERATED_NODE_ID:
                # If at any point we get an enumeration frame after enumeration is finished 
                # it means there is a new node or a node has been reset - so clear our state
                # and start the enumeration process from scratch
                if self.finished:
                    self.reset_state()
                self.__rx_handle_enum_frame(bytes[1:])
            # else:
            #     self.__rx_handle_frame(bytes[1:])
        
        if not self.finished:
            # Finished if we've waited long enough without any more packets, there is more than one nodes
            # and we have either received our own ID back or we are the lowest uuid (and therefore the Master)
            if self.clock.time() > self.finished_time and len(self.sorted_uuids) > 1:
                if self.receivedOwnUuid or self.uuid == self.sorted_uuids[0]:
                    self.finished = True
                    self.id = self.sorted_uuids.index(self.uuid)
            
        

        
# =============================================== #
# Test


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
        

class TestTxWriter:
    def __init__(self, tx_buffer):
        self.tx_buffer = tx_buffer
        
    def write(self, data):
        self.tx_buffer += data
        # print("Data", data)
        # print("New tx frame", self.tx_buffer)

class TestRxReader:
    def __init__(self, rx_buffer):
        self.rx_buffer = rx_buffer
    
    # read back if a full frame is ready (use None to delimit frames)
    def read(self):
        if len(self.rx_buffer) == 0:
            return []
        while self.rx_buffer[0] == None:
            self.rx_buffer.pop(0)
            if len(self.rx_buffer) == 0:
                return []
        if None in self.rx_buffer:
            end = self.rx_buffer.index(None)
            read_data = self.rx_buffer[:end]
            del self.rx_buffer[:end]
            # self.rx_buffer = self.rx_buffer[end:]
            # print("read", read_data)
            # print("rx_buffer", self.rx_buffer)
            return read_data
        else:
            # print("Read nothing")
            return []
    
    # def start_reading(self):
    #     pass
    
    # def stop_reading(self):
    #     pass
        
class TestWire:
    def __init__(self):
        self.tx_buffers = []
        self.rx_buffers = []
    
    def add_node(self, tx_buffer, rx_buffer):
        self.tx_buffers.append(tx_buffer)
        self.rx_buffers.append(rx_buffer)
    
    def update(self):
        # Shift the data out from all the tx buffers
        data = None
        for tx_buffer in self.tx_buffers:
            if len(tx_buffer) > 0:
                if data == None:
                    data = tx_buffer[0]
                else:
                    # Corrupted data - could do something else, like "corrupted" or XOR(self.tx_buffers)
                    data = random.randint(0, 0xFF) 
                tx_buffer.pop(0)
        
        for rx_buffer in self.rx_buffers:
            rx_buffer += [data]


class Node:
    def __init__(self, tx_writer, rx_reader, clock, uuid, max_time_between_enum_frames):
        self.tx_buffer = []
        self.clock = clock
        self.enumeration = EnumerationProtocol(tx_writer, rx_reader, clock, uuid, max_time_between_enum_frames)
    
    def process_rx(self):
        self.enumeration.process_rx()
        
    def process_tx(self):
        self.enumeration.process_tx()
        
    def update_clock(self, ticks):
        self.clock.incr_ticks(ticks)
    
    # Add it to tx buffer
    # def add_data_to_tx_buffer(self, data):
        # self.tx_writer.write(data)


bytes_per_second = 1000000 # 1MBps over the wire

# send a byte per tick
nominal_ticks_per_sec = bytes_per_second
clock_speed_variation = 0.0001 # 100 parts per million


class TestBench:
    max_time_between_enum_frames = 0.005 # at most 5000 bytes between frames -> avg. 2500 bytes which should be plenty
    ticks_betwen_processes = 100 #100us
    
    def __init__(self):
        self.nodes = []
        self.tx_buffers = []
        self.rx_buffers = []
        self.wire = TestWire()
    
    def add_node(self, node_id, ticks_per_sec):
        tx_buffer = []
        rx_buffer = []
        writer = TestTxWriter(tx_buffer)
        reader = TestRxReader(rx_buffer)
        ticks_per_sec = nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * clock_speed_variation)
        clock = Clock(node_id, 0, ticks_per_sec)
        node = Node(writer, reader, clock, node_id, TestBench.max_time_between_enum_frames)
        self.nodes.append(node)
        self.tx_buffers.append(tx_buffer)
        self.rx_buffers.append(rx_buffer)
        self.wire.add_node(tx_buffer, rx_buffer)
    
    def run(self, max_ticks):
        for tick in range(max_ticks):
            for node in self.nodes:
                node.update_clock(1)
            self.wire.update()
            if tick % self.ticks_betwen_processes == 0:
                finished = True
                for node in self.nodes:
                    node.process_rx()
                    node.process_tx()
                    if not node.enumeration.finished:
                        finished = False
                if finished:
                    return True
        return False
        
def test_multiple_static_nodes(num_nodes):
    test = TestBench()
    for node_id in range(0,num_nodes):
        ticks_per_sec = nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * clock_speed_variation)
        test.add_node(node_id, ticks_per_sec)
    max_ticks = int(TestBench.max_time_between_enum_frames * 1000000 * 6 * num_nodes/2)
    finished = test.run(max_ticks)
    
    frame = inspect.currentframe()
    function_name = inspect.getframeinfo(frame).function
    if finished:
        print(function_name, ": Test successful")
    else:
        print(function_name, ": Test failed")

def test_multiple_dynamic_nodes(num_nodes):
    test = TestBench()
    ticks_per_sec = nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * clock_speed_variation)
    test.add_node(num_nodes+1, ticks_per_sec)
    max_ticks = int(TestBench.max_time_between_enum_frames * 1000000 * 6 * num_nodes/2)
    
    ticks = 0
    node_id = 5
    while ticks < max_ticks:
        # Every so often add a new node
        run_ticks = int((max_ticks / num_nodes) * random.random())
        test.run(run_ticks)
        if len(test.nodes) < num_nodes:
            ticks_per_sec = nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * clock_speed_variation)
            test.add_node(node_id, ticks_per_sec)
            node_id += 1
        ticks += run_ticks
    # Finally run for long enough for the protocol to have finished
    finished = test.run(max_ticks)
    
    frame = inspect.currentframe()
    function_name = inspect.getframeinfo(frame).function
    if finished:
        print(function_name, ": Test successful")
    else:
        print(function_name, ": Test failed")
        
test_multiple_static_nodes(10)
test_multiple_dynamic_nodes(10)
    
    # print("node0 receivedOwnUuid", node0.enumeration.receivedOwnUuid)
    # print("node0 finished_time", node0.enumeration.finished_time)
    # print("node0 sorted_uuids", node0.enumeration.sorted_uuids)
    # print("node0 finished", node0.enumeration.finished)
    
    # print("node1 receivedOwnUuid", node1.enumeration.receivedOwnUuid)
    # print("node1 finished_time", node1.enumeration.finished_time)
    # print("node1 sorted_uuids", node1.enumeration.sorted_uuids)
    # print("node1 finished", node1.enumeration.finished)
    

        # uuid.uuid4().int # 128 bit UUID

