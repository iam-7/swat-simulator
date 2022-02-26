import random
import csv
import time
import matplotlib.pyplot as plot

mv_101_states = { 0: "CLOSED", 1: "OPEN"}
p_101_states = { 0: "OFF", 1: "ON"}
high_thres = 800
low_thres = 500

attack_offset = 0.02

L1_list = []
L1_raw_list = []
T1_list = []
S_K_list = []
Z_K_list = []

class AttackDetector:
    def __init__(self, bias, threshold, previous_lit_101, is_attack = False):

        # Variables for Attack Detection (CUSUM)
        self.is_attack_detected = False                      
        self.is_false_alarm = False                    
        self.increment = 0                        
        self.previous_lit_101 = previous_lit_101               
        self.cusum_stat = 0
        self.bias = bias #0.01
        self.threshold = threshold #0.5
        self.is_attack = is_attack
        #print("Bias: {}, threshold: {}".format(self.bias, self.threshold))

    def cusum(self, increment, lit_101):
        if True: #not self.is_attack_detected and not self.is_false_alarm:
            predicted_lit_101 = self.previous_lit_101 + increment
            observation = abs(lit_101 - predicted_lit_101) - self.bias
            self.cusum_stat += observation
            self.previous_lit_101 = lit_101

            if self.cusum_stat < 0:
                self.cusum_stat = 0
            
            if self.cusum_stat > self.threshold:
                if self.is_attack:
                    self.is_attack_detected = True
                else:
                    self.is_false_alarm = True

class Stage1:
    # Constructor for Stage 1
    def __init__(self, curr_level):
        self.lit_101 = curr_level           # Value read by LIT-101 sensor 
        self.mv_101 = mv_101_states[0]      # MV-101 state
        self.p_101 = p_101_states[0]        # P-101 state
        self.t_101 = curr_level             # RW tank level
        self.lit_101_actual = curr_level    # Actual water level in T-101
        self.p_101_is_manual = False
        self.mv_101_is_manual = False

    # PLC controler for stage 1 which controls P-101 and MV-101 based on reading from LIT-101
    def plc_control(self):
        if self.lit_101 > high_thres and not self.mv_101_is_manual:
            self.mv_101 = mv_101_states[0]      # Close MV-101 when LIT-101 reads above high threshold of 800-2
            #self.p_101 = p_101_states[1]

        if self.lit_101 < low_thres and not self.p_101_is_manual:
            self.p_101 = p_101_states[0]        # Turn off P-101 when LIT-101 reads below low threshold of 500+2
            
        if self.lit_101 < low_thres and not self.mv_101_is_manual:
            self.mv_101 = mv_101_states[1]

        if not self.p_101_is_manual:
                self.p_101 = p_101_states[1]        # if LIT-101 reads within threshold keep MV-101 Open and P-101 ON (always need water) 

    # Gets either rise or fall rate of T-101 based on states of MV-101 and P-101
    def get_rate(self):
        if self.mv_101 == mv_101_states[0] and self.p_101 == p_101_states[0]:       # MV-101=CLOSED and P-101=OFF
            fall_rise_rate = 0
            
        elif self.mv_101 == mv_101_states[1] and self.p_101 == p_101_states[1]:     # MV-101=OPEN and P-101=ON
            fall_rise_rate = 1.11857
        elif self.mv_101 == mv_101_states[0] and self.p_101 == p_101_states[1]:     # MV-101=CLOSED and P-101=ON
            fall_rise_rate = -27.40
        elif self.mv_101 == mv_101_states[1] and self.p_101 == p_101_states[0]:     # MV-101=OPEN and P-101=OFF
            fall_rise_rate = 28.5234
        
        return round(fall_rise_rate/60,5)

    # Updates current level of T-101 and states of P-101 and MV-101
    def update_status(self):
        self.plc_control()
        increment_level = self.get_rate()   # rise or fall rate
        self.t_101 += increment_level       # inc/dec T-101 level       
        self.lit_101_actual = self.t_101    # inc/dec LIT-101 actual level       
        self.lit_101 += increment_level     # inc/dec LIT-101 level controller by attacker in attack mode       
        self.plc_control()
        #self.get_curr_stats() 

        return increment_level

    def get_curr_stats(self):
        #print("Current Status of Stage 1:\nLIT-101: {}\nP-101: {}\nMV-101: {}\n".format(self.lit_101, self.p_101, self.mv_101))
        return self.mv_101, self.p_101, self.t_101, self.lit_101, self.lit_101_actual

#Check if actual value of LIT-101/T-101 is under or overflow
def is_under_or_overflow(s1_status):
    is_attack = False
    if s1_status.t_101 > high_thres+5:
        #print("Attack Successful.......# Tank overflow")
        is_attack = True
    elif s1_status.t_101 < low_thres-5:
        #print("Attack Successful.......# Tank Underflow")
        is_attack = True
    
    if is_attack:
        # print("\nCurrent Status of Stage 1:\nLIT-101: {}\nP-101: {}\nMV-101: {}\nT-101: {}\nLIT-101 Actual: {}\n"
        # .format(s1_status.lit_101, s1_status.p_101, s1_status.mv_101, s1_status.t_101, s1_status.lit_101_actual))
        return True

def random_attack(s1_status, is_underflow, is_multipoint_attack = False):
    global attack_offset
    rand = random.randint(1,1000)
    if rand % 6 == 3:
        if not is_underflow:
            s1_status.lit_101 -= attack_offset    # Positive offset will cause underflow and negative offset will cause overflow
        else:
            s1_status.lit_101 += attack_offset
    else:
        attack_offset += random.uniform(-0.01,0.01)
    
    if attack_offset > 0.1:
        attack_offset = 0.01

    if is_multipoint_attack:
        multipoint_attack(s1_status)

# Turing off the P-101 when MV-101 is OPEN and it is approaching the Limit of Tank (790mm)
def multipoint_attack(s1_status):

    if s1_status.lit_101_actual > 795:          # if actual level goes over 790, put P-101 in manual mode and turn it off to cause overflow 
        s1_status.p_101_is_manual = True
        s1_status.p_101 = p_101_states[0]

        if s1_status.lit_101_actual >= 799:     # Make SCADA think think water level is on 799mm
            s1_status.lit_101 = 799
 
def print_baner():
    print("--------------------SWat Stage-1 Simulation----------------------")
    banner_message = """
    1) Simulation for Oneday\n
    2) Simulation for Oneday with Attacks on LIT-101\n
    3) Simulation for Oneday with Multipoint attacks\n
    4) Simulation for Oneday with false positive as function of threshold with fixed bias\n
    5) Simulation for Oneday with attack detection effectiveness as function of bias with fixed threshold\
    """
    print(banner_message)

def print_status(stage1, at):
    print("\n\nStatus of Stage 1 at {}:\nLIT-101: {}\nP-101: {}\nMV-101: {}\nT-101: {}\nLIT-101 Actual: {}\n"
        .format(at, stage1.lit_101, stage1.p_101, stage1.mv_101, stage1.t_101, stage1.lit_101_actual))

def run_simulator(is_attack, is_multipoint_attack, cusum_threshold, cusum_bias):

    # Setting T-101 level to random value 500-700 at start
    start = random.randint(500,700) 
    stage1 = Stage1(start)

    # Making call to PLC to command MV-101 and P-101 based on current LIT-101
    stage1.plc_control()       
    steps = 86400              # Simulation steps 86400 secs => 1 Day
    current_step = 0

    # Attack variables
    attack_start_point = random.randint(0, steps//2)

    is_attack_requested = is_attack
    is_attack = False
    is_attack_success = False

    attack_detector = AttackDetector(cusum_bias, cusum_threshold, stage1.lit_101, is_attack)
    
    #output_file = "s1_dataset_mode_" + str(run_option) + "_" + time.strftime("%Y%m%d-%H%M%S") + ".csv"
    #headers = ['time','MV-101','P-101','T-101','LIT-101','LIT-101-Actual']
    #stage1_dataset = open(output_file,"w")
    #dataset_writter = csv.writer(stage1_dataset)
    #dataset_writter.writerow(headers)
    #print_status(stage1, "Start")
    
    while current_step <= steps:
        
        increment = stage1.update_status()

        if is_attack_requested and not is_attack:
            if current_step == attack_start_point:
                is_attack = True
                attack_detector.is_attack = is_attack
        if not is_attack_requested and is_attack:
            is_attack = False

        if is_attack:
            random_attack(stage1, False, is_multipoint_attack) # adding random offset value to LIT-101 that is read by SCADA

        if current_step%3 == 0: stage1.lit_101 += 0.001 # adding noice

        attack_detector.cusum(increment, stage1.lit_101)

        if is_under_or_overflow(stage1):     # Check if actual value of LIT-101/T-101 is under or overflow
            #curr_states.append("Attack")
            #dataset_writter.writerow(curr_states)
            #stage1.get_curr_stats()
            is_attack_success = True
            break
        
        #mv_101, p_101, t_101, lit_101, lit_101_actual = stage1.get_curr_stats()
        #curr_states = [current_step, mv_101, p_101, t_101, lit_101, lit_101_actual]
        #dataset_writter.writerow(curr_states)

        current_step += 1
    mv_101, p_101, t_101, lit_101, lit_101_actual = stage1.get_curr_stats()
    curr_states = [current_step, mv_101, p_101, t_101, lit_101, lit_101_actual]
    return stage1, is_attack_success, attack_detector.is_attack_detected, attack_detector.is_false_alarm

if __name__ == '__main__':
    print_baner()
    run_option = int(input("Select Option to start the simulation(1-5):"))

    if run_option == 1:
        is_attack = False
        is_multipoint_attack = False
        bias = 0.01
        threshold = 0.5
        curr_states, is_attack_success, is_attack_detected, is_false_alarm = run_simulator(is_attack, is_multipoint_attack, threshold, bias)

       
        print("**************** Simulation of Swat without Attack ****************")
        print_status(curr_states, "End")
    
    elif run_option == 2:
        is_attack = True
        is_multipoint_attack = False
        bias = 0.01
        threshold = 0.5
        num_attack_detected = 0
        num_false_alarms = 0
        curr_states, is_attack_success, is_attack_detected, is_false_alarm = run_simulator(is_attack, is_multipoint_attack, threshold, bias)

        

        if is_attack_detected:
            num_attack_detected = 1
        
        if is_false_alarm:
            num_false_alarms = 1
       
        print("\n**************** Simulation of Swat with random Attack ****************")
        print_status(curr_states, "End")
        print("Attacks detected..........:", num_attack_detected)
        print("Fasle Alarms..............:", num_false_alarms)

    elif run_option == 3:
        is_attack = True
        is_multipoint_attack = True
        bias = 0.01
        threshold = 0.5
        num_attack_detected = 0
        num_false_alarms = 0
        curr_states, is_attack_success, is_attack_detected, is_false_alarm = run_simulator(is_attack, is_multipoint_attack, threshold, bias)

        if is_attack_detected:
            num_attack_detected = 1
        
        if is_false_alarm:
            num_false_alarms = 1
       
        print("\n**************** Simulation of Swat with random Multipoint Attack ****************")
        print_status(curr_states, "End")
        print("Attacks detected..........:", num_attack_detected)
        print("Fasle Alarms..............:", num_false_alarms)
    
    elif run_option == 4:
        is_attack = True
        is_multipoint_attack = False
        bias = 0.005 # 0.005
        threshold = 0.01
        num_of_simulations = 15
        list_of_thresholds = list()
        list_of_false_positive = list()
        print("\n**************** Simulation of Swat with Attack and False alarm rate as a function of threshold ****************")
        while threshold < 2:
            num_attack_detected = 0
            num_false_alarms = 0
            curr_run = 1
            while curr_run <= num_of_simulations:

                curr_states, is_attack_success, is_attack_detected, is_false_alarm = run_simulator(is_attack, is_multipoint_attack, threshold, bias)

                if is_attack_detected:
                    num_attack_detected += 1
                
                if is_false_alarm:
                    num_false_alarms += 1
                curr_run += 1
            list_of_thresholds.append(threshold)
            list_of_false_positive.append(round(num_false_alarms/num_of_simulations, 2))
            print("\n#Threshold={} Total Simulations #{}\n".format(threshold, num_of_simulations)) 
            print("# Number of False Alarms..........: ", num_false_alarms) 
            print("# Number of Attacks Detected......: ", num_attack_detected)
            print("# False Alarm Rate................: ",round(num_false_alarms/num_of_simulations, 2))
            threshold += 0.01

        plot.plot(list_of_false_positive, list_of_thresholds)
        plot.title("False Positive Rate as a function of Threshold")
        plot.xlabel("False Positive Rate")
        plot.ylabel("Threshold")
        plot.show()
    
    elif run_option == 5:
        is_attack = True
        is_multipoint_attack = False
        bias = 0.00
        threshold = 0.1 # 0.1
        num_of_simulations = 15
        list_of_bias = list()
        list_of_detection = list()
        list_of_false_alarm = list()
        tot_num_attack_detected = 0
        tot_attacks = 0

        print("\n**************** Simulation of Swat with Attack and Attack Detection effectiveness as function of bias ****************")
        while bias < 0.05:
            num_attack_detected = 0
            num_false_alarms = 0
            curr_run = 1
            while curr_run <= num_of_simulations:

                curr_states, is_attack_success, is_attack_detected, is_false_alarm = run_simulator(is_attack, is_multipoint_attack, threshold, bias)

                if is_attack_detected:
                    num_attack_detected += 1

                if is_false_alarm:
                    num_false_alarms += 1
                curr_run += 1
            list_of_bias.append(bias)
            list_of_detection.append(num_attack_detected/num_of_simulations)
            list_of_false_alarm.append(num_false_alarms/num_of_simulations)
            tot_num_attack_detected += num_attack_detected
            tot_attacks += num_of_simulations
            bias += 0.005
        
        print("The Maximum Detection Effectiveness is at", max(list_of_detection)*100, "%",
              " when bias is at %.3f" % list_of_bias[list_of_detection.index(max(list_of_detection))])
        print("False alarm rate", list_of_false_alarm[list_of_detection.index(max(list_of_detection))])
        #print("Attack detection effectiveness: ",(tot_num_attack_detected/tot_attacks))
    exit()
    #     mv_101, p_101, t_101, lit_101, lit_101_actual = stage1.get_curr_stats()
    #     curr_states = [current_step, mv_101, p_101, t_101, lit_101, lit_101_actual]
    #     dataset_writter.writerow(curr_states)




 