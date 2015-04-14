import socket as sck


class Pipe():

    def __init__(self, name, type):
        self.name = name
        self.type = type
        self._sock = sck.socket(sck.AF_INET, sck.SOCK_STREAM)

    def connect(self, addr):
        while
