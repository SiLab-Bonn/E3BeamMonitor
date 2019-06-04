from __future__ import print_function
from basil.dut import Dut
import time



dut = Dut('/home/rasmus/git/basil/examples/lab_devices/ttiql355tp.yaml')
dut.init()
print(dut['PowerSupply'].get_name())

def power_on():
    dut['PowerSupply'].on(channel=1)
    dut['PowerSupply'].on(channel=2)
    dut['PowerSupply'].on(channel=3)

    time.sleep(3)

    print ("Channel 1")
    print(dut['PowerSupply'].get_voltage(channel=1))    
    print ("Channel 2")
    print(dut['PowerSupply'].get_voltage(channel=2))


def power_off():
    dut['PowerSupply'].off(channel=1)
    dut['PowerSupply'].off(channel=2)
    dut['PowerSupply'].off(channel=3)

    time.sleep(3)

    print ("Channel 1")
    print(dut['PowerSupply'].get_voltage(channel=1))    
    print ("Channel 2")
    print(dut['PowerSupply'].get_voltage(channel=2))
    
    
def voltage_channel1():
    return dut['PowerSupply'].get_voltage(channel=1)

def voltage_channel2():
    return dut['PowerSupply'].get_voltage(channel=2)



#print (voltage_channel1())
#print (voltage_channel2())
power_off()

#dut['PowerSupply'].set_voltage(1.2,channel=1) 
#dut['PowerSupply'].set_voltage(1.5,channel=2)




