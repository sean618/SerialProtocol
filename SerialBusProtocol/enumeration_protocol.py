import random
import inspect
import test_node

# TODO: make more settings configurable
NUM_UUID_BYTES = 1
UNENUMERATED_NODE_ID = 0xFF

# Protocol to discover all connected nodes on a shared bus - handling nodes potentially transmitting at the same time
class EnumerationProtocol:
    
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
        self.id = UNENUMERATED_NODE_ID
    
    def __tx_enum_frame(self):
        # print("Time:", self.clock.time(), "Tx enum frame, UUID:", self.uuid)
        frame = int(UNENUMERATED_NODE_ID).to_bytes(1, byteorder='little')
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
            if bytes[0] == UNENUMERATED_NODE_ID:
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


##########################################################

class TestBench:
    # TODO
    bytes_per_second = 1000000 # 1MBps over the wire

    # send a byte per tick
    nominal_ticks_per_sec = bytes_per_second
    clock_speed_variation = 0.0001 # 100 parts per million

    max_time_between_enum_frames = 0.005 # at most 5000 bytes between frames -> avg. 2500 bytes which should be plenty
    ticks_betwen_processes = 100 #100us
    
    def __init__(self):
        self.nodes = []
        self.wire = test_node.TestWire()
    
    def create_nodes(self, num):
        for node_id in range(num):
            ticks_per_sec = TestBench.nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * TestBench.clock_speed_variation)
            clock = test_node.Clock(node_id, 0, ticks_per_sec)
            writer = test_node.TestTxWriter()
            reader = test_node.TestRxReader()
            protocol = EnumerationProtocol(writer, reader, clock, node_id, TestBench.max_time_between_enum_frames)
            node = test_node.Node(writer, reader, clock, protocol)
            self.nodes.append(node)
            self.wire.add_node(node)
    
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
                    if not node.protocol.finished:
                        finished = False
                if finished:
                    return True
        return False
        
def test_multiple_static_nodes(num_nodes):
    test = TestBench()
    test.create_nodes(num_nodes)
    max_ticks = int(TestBench.max_time_between_enum_frames * 1000000 * 6 * num_nodes/2)
    finished = test.run(max_ticks)
    
    frame = inspect.currentframe()
    function_name = inspect.getframeinfo(frame).function
    if finished:
        print(function_name, ": Test successful")
    else:
        print(function_name, ": Test failed")

# def test_multiple_dynamic_nodes(num_nodes):
#     test = TestBench()
#     ticks_per_sec = nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * clock_speed_variation)
#     test.add_node(num_nodes+1, ticks_per_sec)
#     max_ticks = int(TestBench.max_time_between_enum_frames * 1000000 * 6 * num_nodes/2)
    
#     ticks = 0
#     node_id = 5
#     while ticks < max_ticks:
#         # Every so often add a new node
#         run_ticks = int((max_ticks / num_nodes) * random.random())
#         test.run(run_ticks)
#         if len(test.nodes) < num_nodes:
#             ticks_per_sec = nominal_ticks_per_sec * (1 + (random.random() * 2 - 1) * clock_speed_variation)
#             test.add_node(node_id, ticks_per_sec)
#             node_id += 1
#         ticks += run_ticks
#     # Finally run for long enough for the protocol to have finished
#     finished = test.run(max_ticks)
    
#     frame = inspect.currentframe()
#     function_name = inspect.getframeinfo(frame).function
#     if finished:
#         print(function_name, ": Test successful")
#     else:
#         print(function_name, ": Test failed")
        
test_multiple_static_nodes(10)
# test_multiple_dynamic_nodes(10)

    