import test_node
import random
import traceback

# TODO: support nodes having different integer multiples of the time slot.
#       This could be done as an initialisation stage where every node sends,
#       in turn, a list of all known slot multiples including it's own.
class TimeDivisionMultiplexingProtocol:
    
    SYNC_PACKET_TYPE = 0xAA
    
    def __init__(self, clock, writer, reader, node_id, num_nodes, time_per_node, time_between_sync_packets, time_for_tx_to_reach_rx, time_margin):
        self.time_for_tx_to_reach_rx = time_for_tx_to_reach_rx
        self.time_margin = time_margin
        self.time_between_sync_packets = time_between_sync_packets
        
        self.writer = writer
        self.reader = reader
        self.clock = clock
        self.num_nodes = num_nodes
        self.node_id = node_id
        self.time_per_node = time_per_node
        self.cycle_period = num_nodes * time_per_node
        self.start_tx_time = node_id * time_per_node
        self.end_tx_time = (node_id + 1) * time_per_node - time_margin
        self.next_sync_time = 0
        
    def tx_sync_packet(self):
        frame = int(self.SYNC_PACKET_TYPE).to_bytes(1, byteorder='little')
        # Convert time into pico seconds and pack it into 16 bytes
        frame = int(self.clock.time() * 1000*1000*1000*1000).to_bytes(10, byteorder='little')
        print("Sent time", self.clock.time())
        self.writer.write(frame)
        
    def handle_rx_sync_packet(self, bytes):
        sent_time = int.from_bytes(bytes, byteorder='little') / (1000*1000*1000*1000)
        print("Received time", sent_time)
        expected_time_now = sent_time + self.time_for_tx_to_reach_rx
        # Move the clock to between the expected time and our current time
        new_time = self.clock.time() + (expected_time_now - self.clock.time())/2 
        self.clock.set_time(new_time)
    
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
            self.__handle_sync_packet(bytes[1:])


##################################
# Test

class TestWriter:
    def __init__(self, all_connected_readers):
        self.readers = all_connected_readers
        self.max_bytes = 1000 # Send up to this many bytes at a time
        
    def write(self, data):
        for reader in self.readers:
            # Corruption
            if random.random() < 1/20:
                index = random.randint(0, len(data)-1)
                data[index] = 0
            reader.buffer = reader.buffer + data

class TestReader:
    def __init__(self):
        self.buffer = []
    
    def read(self):
        data = self.buffer[:]
        self.buffer = []
        return data


def basic_test():
    frames = []
    class TmpWriter:
        def write(self, data):
            frames.append(data)

    ticks_per_sec = 1000*1000
    clock0 = test_node.Clock(0, 0, ticks_per_sec)
    protocol0 = TimeDivisionMultiplexingProtocol(clock0, TmpWriter(), None, 0, 1, 1, 1, 0, 0)
    protocol0.tx_sync_packet()
    test_ticks = 1000
    clock1 = test_node.Clock(0, test_ticks, ticks_per_sec)
    protocol1 = TimeDivisionMultiplexingProtocol(clock1, TmpWriter(), None, 0, 1, 1, 1, 0, 0)
    protocol1.handle_rx_sync_packet(frames[0][1:])
    print(clock1.ticks, test_ticks)
    assert clock1.ticks == test_ticks/2
    

if __name__ == "__main__":
    tests = [basic_test]
    tests_passed = 0
    for test in tests:
        try:
            test()
            tests_passed += 1
        except:
            traceback.print_exc()
            print(test, ": Test failed")
            continue
    print("{}/{} Tests succeeded".format(tests_passed, len(tests)))




