"""
Consistent Overhead Byte Stuffing (COBS)

Taken from https://raw.githubusercontent.com/cmcqueen/cobs-python/main/python3/cobs/cobs/_cobs_py.py

This version is for Python 3.x.
"""


class DecodeError(Exception):
    pass


def _get_buffer_view(in_bytes):
    mv = memoryview(in_bytes)
    if mv.ndim > 1 or mv.itemsize > 1:
        raise BufferError('object must be a single-dimension buffer of bytes.')
    try:
        mv = mv.cast('c')
    except AttributeError:
        pass
    return mv

def encode(in_bytes):
    """Encode a string using Consistent Overhead Byte Stuffing (COBS).
    
    Input is any byte string. Output is also a byte string.
    
    Encoding guarantees no zero bytes in the output. The output
    string will be expanded slightly, by a predictable amount.
    
    An empty string is encoded to '\\x01'"""
    if isinstance(in_bytes, str):
        raise TypeError('Unicode-objects must be encoded as bytes first')
    in_bytes_mv = _get_buffer_view(in_bytes)
    final_zero = True
    out_bytes = bytearray()
    idx = 0
    search_start_idx = 0
    for in_char in in_bytes_mv:
        if in_char == b'\x00':
            final_zero = True
            out_bytes.append(idx - search_start_idx + 1)
            out_bytes += in_bytes_mv[search_start_idx:idx]
            search_start_idx = idx + 1
        else:
            if idx - search_start_idx == 0xFD:
                final_zero = False
                out_bytes.append(0xFF)
                out_bytes += in_bytes_mv[search_start_idx:idx+1]
                search_start_idx = idx + 1
        idx += 1
    if idx != search_start_idx or final_zero:
        out_bytes.append(idx - search_start_idx + 1)
        out_bytes += in_bytes_mv[search_start_idx:idx]
    return bytes(out_bytes)


def decode(in_bytes):
    """Decode a string using Consistent Overhead Byte Stuffing (COBS).
    
    Input should be a byte string that has been COBS encoded. Output
    is also a byte string.
    
    A cobs.DecodeError exception will be raised if the encoded data
    is invalid."""
    if isinstance(in_bytes, str):
        raise TypeError('Unicode-objects are not supported; byte buffer objects only')
    in_bytes_mv = _get_buffer_view(in_bytes)
    out_bytes = bytearray()
    idx = 0

    if len(in_bytes_mv) > 0:
        while True:
            length = ord(in_bytes_mv[idx])
            if length == 0:
                raise DecodeError("zero byte found in input")
            idx += 1
            end = idx + length - 1
            copy_mv = in_bytes_mv[idx:end]
            if b'\x00' in copy_mv:
                raise DecodeError("zero byte found in input")
            out_bytes += copy_mv
            idx = end
            if idx > len(in_bytes_mv):
                raise DecodeError("not enough input bytes for length code")
            if idx < len(in_bytes_mv):
                if length < 0xFF:
                    out_bytes.append(0)
            else:
                break
    return bytes(out_bytes)








# # Consistent Overhead Byte Stuffing protocol
# # Used to delimit packets in a constant stream of bytes
# import traceback

# # Simple because it only handles packet lengths up to 255
# class SimpleCobsProtocol:
    
#     DELIMITING_BYTE = 0x0 # TODO: put back to 0 at some point
    
#     def encode(self, frame):
#         assert len(frame) < 256
#         encoded = frame.copy()
#         bytes_till_next_replacement = 0
#         # Go through array from back to front
#         for i in reversed(range(len(encoded))):
#             bytes_till_next_replacement += 1
#             # Every instance of the delimiting byte found replace with the number of bytes it is to the next delimiting byte
#             if encoded[i] == self.DELIMITING_BYTE:
#                 encoded[i] = bytes_till_next_replacement
#                 bytes_till_next_replacement = 0
#         # Add an extra byte to point to the first delimiter in the data
#         encoded.insert(0, bytes_till_next_replacement+1)
#         # Now we've replaced all occurences of the special delimiting byte from the data we can use it as a encoded delimiter
#         encoded.append(self.DELIMITING_BYTE)
#         return encoded
    
#     # Return decoded_frame
#     def decode(self, data):
#         if len(data) == 0:
#             return (False, None)
#         frame = data.copy()
#         # # Strip off first byte
#         # if frame[0] == self.DELIMITING_BYTE:
#         #     frame.pop(0)
#         # Check we have a full frame to work on
#         if self.DELIMITING_BYTE not in frame:
#             return (False, None)
#         end = frame.index(self.DELIMITING_BYTE)
#         if end >= 256:
#             print("Corrupted COBS - over length", end)
#             return (False, frame[1:end])
        
#         # The first byte is the number of frame before the next replaced byte
#         # Go to that position and replace it then repeat until the end of the packet
#         index = 0
#         while index < end:
#             bytes_till_next_replacement = frame[index]
#             frame[index] = self.DELIMITING_BYTE
#             index += bytes_till_next_replacement
#         if index != end:
#             print("Corrupted COBS", index, end)
#             # print(data)
#             # print(frame)
#             # assert 0
#             return (False, frame[1:end])
#         return (True, frame[1:end])
    


# def basic_test():
#     cobs = SimpleCobsProtocol()
#     data = bytearray([i for i in range(0,253)])
#     encoded = cobs.encode(data)
#     assert encoded[-1] == cobs.DELIMITING_BYTE
#     for byte in encoded[:-1]:
#         assert byte != cobs.DELIMITING_BYTE
#     decoded = cobs.decode(encoded)
#     # print(num_bytes, len(data))
#     # print(decoded)
#     # print(data)
#     assert data == decoded

# if __name__ == "__main__":
#     tests = [basic_test]
#     tests_passed = 0
#     for test in tests:
#         try:
#             test()
#             tests_passed += 1
#         except:
#             traceback.print_exc()
#             print(test, ": Test failed")
#             continue
#     print("{}/{} Tests succeeded".format(tests_passed, len(tests)))






        
        
        

