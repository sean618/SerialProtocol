# Sliding window protocol
# Used to ensure packets are send reliably and in order.

import cobs
import crc
import test_node
import random
import traceback

# Frames are encoded as:
# dst+1, dst+1, cobs0, src, data0, ... , dataN, crc0, crc1, 0
# The data and src byte are CRC'd and then COBS encoded
# The destination is then added to the front so it can be read without running COBS
# But this means the destination cannot be 0, so we add 1 to it
# As the destination is also outside the CRC we duplicate it

def encode_frame(src, dst, frame):
    encoded = [src] + frame
    crc16 = crc.calc16(0, encoded)
    crc_byte0 = crc16 & 0xFF
    crc_byte1 = (crc16 >> 8) & 0xFF
    encoded = encoded + [crc_byte0, crc_byte1]
    encoded = list(cobs.encode(bytearray(encoded))) + [0]
    assert dst < 255
    encoded = [dst+1, dst+1] + encoded # Add 1 to the destination to make sure it's never 0
    return encoded

def decode_frame(rx_bytes):
    no_result = (None, None, None)
    # Get frame up to delimiter
    if 0 not in rx_bytes:
        return no_result
    end = rx_bytes.index(0)
    frame = rx_bytes[:end]
    del rx_bytes[:end+1]
    if len(frame) < 5:
        return no_result
    # Check destination bytes
    dst = frame.pop(0)-1
    dst_check = frame.pop(0)-1
    if dst != dst_check:
        return no_result
    # COBS decode
    try:
        frame = list(cobs.decode(bytearray(frame)))
    except cobs.DecodeError:
        return no_result
    # Check CRC
    crc_byte1 = frame.pop(-1)
    crc_byte0 = frame.pop(-1)
    crc16 = (crc_byte1 << 8) | crc_byte0
    if crc16 != crc.calc16(0, frame):
        return no_result
    assert len(frame) > 1
    src = frame.pop(0)
    return (src, dst, frame)


class ByteBuffer:
    
    def __init__(self, size):
        self.buffer = []
        self.frame_lengths = []
        self.size = size
        
    def add_frame(self, src, dst, frame):
        encoded = encode_frame(src, dst, frame)
        if len(encoded) + len(self.buffer) < self.size:
            self.buffer += encoded
            self.frame_lengths.append(len(encoded))
    
    def pop_next_frames(self, max_bytes):
        num_bytes = 0
        while (len(self.frame_lengths) > 0) and (num_bytes + self.frame_lengths[0] <= max_bytes):
            length = self.frame_lengths.pop(0)
            num_bytes += length
        if num_bytes == 0:
            return None
        data = self.buffer[:num_bytes]
        self.buffer = self.buffer[num_bytes:]
        return data


class SlidingWindowByteBuffer:
    
    def __init__(self, size, window_size, node_id):
        self.node_id = node_id
        self.buffer = []
        self.frame_info = [] # [(id, dst, length)]
        self.current_pos = 0
        self.size = size
        self.window_size = window_size
    
    def end_of_window(self):
        return ((self.current_pos >= self.window_size) or (self.current_pos >= len(self.frame_info)))
        
    def get_next_frames(self, max_bytes):
        if self.end_of_window():
            self.current_pos = 0
        num_bytes = 0
        first_pos = self.current_pos
        while len(self.frame_info) > 0 and not self.end_of_window():
            (id, dst, length) = self.frame_info[self.current_pos]
            if num_bytes + length > max_bytes:
                break
            num_bytes += length
            self.current_pos += 1
        if num_bytes == 0:
            return None
        # Work out the starting byte position
        start = 0
        for i in range(first_pos):
            (id, dst, length) = self.frame_info[i]
            start += length
        return self.buffer[start:(start+num_bytes)]
    
    def __find_dst_id_in_buffer(self, dst, id):
        i = 0
        for info in self.frame_info:
            i += 1
            (id0, dst0, length0) = info
            if dst == dst0 and id == id0:
                return i
        return 0
    
    # Go through the list of frames and acknowledge everything up to this id and destination
    def ack_frame(self, dst, id):
        if len(self.frame_info) > 0:
            # Check if acked ID actually exists in the queue
            end = self.__find_dst_id_in_buffer(dst, id)
            if end > 0:
                num_acked = 0
                for i in range(end):
                    (id0, dst0, length0) = self.frame_info[i]
                    if dst0 != dst:
                        # The point where we encounter a frame to a different destination
                        # We need to stop and wait for that ack before continuing
                        break
                    self.buffer = self.buffer[length0:]
                    if self.current_pos > 0:
                        self.current_pos -= 1
                    num_acked += 1
                del self.frame_info[:num_acked]
        
    def add_frame(self, src, dst, id, frame):
        encoded = encode_frame(src, dst, frame)
        if len(encoded) + len(self.buffer) < self.size:
            self.buffer += encoded
            self.frame_info.append((id, dst, len(encoded)))
        else:
            assert 0 # TODO
    
        

class WindowedProtocol:
    
    # TODO: pass in
    TX_DIRECT_BUFFER_SIZE = 100000
    TX_WINDOW_BUFFER_SIZE = 100000
    WINDOW_SIZE = 10 # TODO: should this be in bytes?
    WRAP_TIME = 0.001 # 1ms
    
    # Requests 
    INITIALISE = 0x02
    FRAME = 0x03
    # Responses
    UNINITIALISED = 0x82
    INITIALISED = 0x83
    ACK = 0x84
    
    
    def __init__(self, id, clock, connected_ids, writer, reader) -> None:
        self.verbose = 0
        self.id = id
        self.rx_bytes = []
        self.clock = clock
        self.writer = writer
        self.reader = reader
        
        self.tx_window_buffer = SlidingWindowByteBuffer(self.TX_WINDOW_BUFFER_SIZE, self.WINDOW_SIZE, id)
        self.tx_direct_buffer = ByteBuffer(self.TX_DIRECT_BUFFER_SIZE) # For direct frames and responses
        self.time_end_reached = 0
        # Per destination attributes
        self.tx_sequence_num = {}
        self.exp_rx_sequence_num = {}
        self.egress_initialised = {}
        self.ingress_initialised = {}
        self.rx_frames = {}
        for dst in connected_ids:
            self.tx_sequence_num[dst] = 0
            self.exp_rx_sequence_num[dst] = 0
            self.egress_initialised[dst] = False
            self.ingress_initialised[dst] = False
            self.rx_frames[dst] = []
    
    def __tx_responses(self, max_bytes):
        data = self.tx_direct_buffer.pop_next_frames(max_bytes)
        if data == None:
            return 0
        if self.verbose > 1:
            print(self.id, "Response: Sending", data)
        self.writer.write(data)
        return len(data)
    
    def __tx_requests(self, max_bytes):
        # If reached the end of the window pause before starting from the beginning
        if self.tx_window_buffer.end_of_window():
            if self.time_end_reached == 0:
                self.time_end_reached = self.clock.time()
            if self.clock.time() < self.time_end_reached + self.WRAP_TIME:
                return 0
            else:
                self.time_end_reached = 0
                if self.verbose > 1:
                    print(self.id, "Wrapped")
        data = self.tx_window_buffer.get_next_frames(max_bytes)
        if data == None:
            return 0
        if self.verbose > 1:
            print(self.id, "Requests: Sending", data)
        self.writer.write(data)
        return len(data)
    
    def process_tx(self):
        for dst in self.egress_initialised.keys():
            # Send an init request - but limit it to as many inits in the queue as there are connections
            # so we don't overload the other side
            if not self.egress_initialised[dst] and len(self.tx_window_buffer.frame_info) < len(self.egress_initialised.keys()):
                    frame = [self.INITIALISE, self.tx_sequence_num[dst]]
                    if self.verbose > 0:
                        print(self.id, dst, "Send init", frame)
                    self.tx_direct_buffer.add_frame(self.id, dst, frame)
        bytes_left = self.writer.max_bytes
        # First transmit direct frames/responses (not too many otherwise one side gets all the bandwidth)
        bytes_left -= self.__tx_responses(bytes_left/2)
        # Now transmit the ordered frames
        bytes_left -= self.__tx_requests(bytes_left)
        # Now if there is any space left try and fit in more direct frames/responses
        bytes_left -= self.__tx_responses(bytes_left)
    
    # Returns number of frames successfully submitted
    def submit_tx_frames(self, dst, frames):
        # Only allow frames to be sent once all connections are initialised
        # So we don't block any init requests with data
        for initialised in self.egress_initialised:
            if not initialised:
                return 0
        if self.verbose > 0:
            print(self.id, dst, "Submitting", len(frames), "frames")
        for bare_frame in frames:
            frame = bare_frame.copy()
            frame.insert(0, self.FRAME)
            frame.append(self.tx_sequence_num[dst])
            self.tx_window_buffer.add_frame(self.id, dst, self.tx_sequence_num[dst], frame)
            self.tx_sequence_num[dst] = (self.tx_sequence_num[dst] + 1) % 256
        return len(frames)
        
    def __handle_request(self, src, type, data):
        if self.verbose > 1:
            print(self.id, src, "Incoming frame:", data)
        response = None
        if type == self.FRAME:
            if self.ingress_initialised[src]:
                sequence_num = data.pop(-1)
                if self.verbose > 0:
                    print(self.id, src, "Received frame - seq", sequence_num)
                if sequence_num == self.exp_rx_sequence_num[src]:
                    response = [self.ACK, sequence_num]
                    self.exp_rx_sequence_num[src] = (sequence_num + 1) % 256
                    self.rx_frames[src].append(data)
                else:
                    response = [self.ACK, (self.exp_rx_sequence_num[src] - 1) % 256]
                    # Invalid sequence num
                    pass
            else:
                response = [self.UNINITIALISED, 0]
                if self.verbose > 0:
                    print(self.id, src, "Response uninit")
        elif type == self.INITIALISE:
            self.exp_rx_sequence_num[src] = data[0]
            self.ingress_initialised[src] = True
            response = [self.INITIALISED, 0]
            if self.verbose > 0:
                print(self.id, src, "Response init", response)
        else:
            print("Invalid request type")
            assert 0
        if response != None:
            assert len(response) == 2
            self.tx_direct_buffer.add_frame(self.id, src, response)
    
    def __handle_response(self, src, type, data):
        if type == self.ACK:
            if self.verbose > 0:
                print(self.id, src, "Received ack", data[0])
            self.tx_window_buffer.ack_frame(src, data[0])
        elif type == self.UNINITIALISED:
            if self.egress_initialised[src]:
                self.egress_initialised[src] = False
        elif type == self.INITIALISED:
            self.egress_initialised[src] = True
        else:
            print("Invalid response type")
            assert 0
    
    def __handle_rx_frame(self, src, frame):
        frame_type = frame.pop(0)
        frame_data = frame
        if (frame_type & 0x80) == 0x80:
            self.__handle_response(src, frame_type, frame_data)
        else:
            self.__handle_request(src, frame_type, frame_data)
    
    def process_rx(self):
        self.rx_bytes += self.reader.read()
        while True:
            # if self.verbose:
            #     print(self.id, "rx bytes frame:", self.rx_bytes)
            (src, dst, frame) = decode_frame(self.rx_bytes)
            if frame == None:
                break
            if dst == self.id:
                self.__handle_rx_frame(src, frame)
    
    def get_rx_frames(self, src):
        frames = self.rx_frames[src][:]
        self.rx_frames[src] = []
        return frames
            
    
##########################
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

class TestBench:
    bytes_per_second = 1000000 # 1MBps over the wire
    ticks_per_sec = bytes_per_second # send a byte per tick
    ticks_betwen_processes = 100 #100us
    
    def __init__(self):
        self.nodes = []
        self.clock = test_node.Clock(0, 0, self.ticks_per_sec)
    
    def create_nodes(self, num):
        readers = []
        ids = []
        for i in range(num):
            readers.append(TestReader())
            ids.append(i)
        for i in range(num):
            # Remove the current node from the list of connected nodes (otherwise it's basically in loopback)
            connected_readers = readers[:]
            connected_readers.pop(i)
            connected_ids = ids[:]
            connected_ids.pop(i)
            writer = TestWriter(connected_readers)
            protocol = WindowedProtocol(i, self.clock, connected_ids, writer, readers[i])
            self.nodes.append(protocol)
            
    
    def run_till_initialised(self, max_ticks):
        for tick in range(max_ticks):
            self.clock.incr_ticks(1)
            if tick % self.ticks_betwen_processes == 0:
                finished = True
                for i in range(len(self.nodes)):
                    node = self.nodes[i]
                    node.process_rx()
                    node.process_tx()
                    for k in range(len(self.nodes)):
                        if k != i:
                            if not node.egress_initialised[k] or not node.ingress_initialised[k]:
                                finished = False
                if finished:
                    break
        if not finished:
            print("Failed to initialise")
            assert 0
    
    def run(self, total_num_frames, max_ticks):
        for tick in range(max_ticks):
            self.clock.incr_ticks(1)
            if tick % self.ticks_betwen_processes == 0:
                sum = 0
                for rx in range(len(self.nodes)):
                    node = self.nodes[rx]
                    node.process_rx()
                    node.process_tx()
                    for tx in range(len(self.nodes)):
                        if tx != node.id:
                            sum += len(node.rx_frames[tx])
                if sum == total_num_frames:
                    return True
        return False

def basic_test():
    # Create frames
    num_nodes = 5
    num_frames = 100
    max_frame_length = 240
    frames_from_to = [[[] for i in range(num_nodes)] for i in range(num_nodes)]
    for tx in range(num_nodes):
        for rx in range(num_nodes):
            frames = []
            for f in range(num_frames):
                frames.append([random.randint(0,255) for i in range(random.randint(0, max_frame_length))])
            frames_from_to[tx][rx] = frames
    
    # Run tests
    test = TestBench()
    test.create_nodes(num_nodes)
    test.run_till_initialised(10000)
    num_frames = 0
    for tx in range(num_nodes):
        for rx in range(num_nodes):
            if rx != tx:
                test.nodes[tx].submit_tx_frames(rx, frames_from_to[tx][rx])
                num_frames += len(frames_from_to[tx][rx])
    success = test.run(num_frames, 10000000)
    if not success:
        print("Test finished before all frames received")
        assert 0
    
    # Check results
    for tx in range(num_nodes):
        for rx in range(num_nodes):
            if rx != tx:
                got = test.nodes[rx].get_rx_frames(tx)
                exp = frames_from_to[tx][rx]
                print("Frames from", tx, "to", rx, ":", len(got))
                for i in range(len(exp)):
                    if got[i] != exp[i]:
                        print("Tx", tx, "Rx", rx, "Frame", i, "- did not match")
                        print("Tx", exp[i])
                        print("Rx", got[i])
                        assert 0
    
    

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






        
        
        

