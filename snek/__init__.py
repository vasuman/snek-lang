import parser
import target
import net
import events

load_file = parser.load_file

def start_reactor():
    r = events.Reactor()
    import threading
    t = threading.Thread(target = r.run)
    t.start()
    return r

