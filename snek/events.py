from Queue import Queue

class EventReactor(object):
    def __init__(self, namespace):
        self._namespace = namespace
        self.running = False
        self.event_queue = Queue()

    def run(self):
        self.running = True
        while self.running:
            event = event_queue.get()

    def transition(self, mod, state):
        
