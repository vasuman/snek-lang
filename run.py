import snek
import time
import sys

HOUR = 60 * 60

def main():
    fname = sys.argv[1]
    modules = sys.argv[2:]
    with open(fname, 'rb') as f:
        sf = snek.load_file(f)
    r = snek.start_reactor()    
    for module in modules:
        mod = sf.get_module(module)
        r.init(mod)
    try:
        time.sleep(HOUR)
    except KeyboardInterrupt:
        r.stop()


if __name__ == '__main__':
    main()
