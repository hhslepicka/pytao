import sys
import os
import re
import io
import pexpect
import time
if 'ACC_LOCAL_ROOT' in os.environ.keys():
    sys.path.append(os.environ['ACC_LOCAL_ROOT']+'/tao/python/')
elif 'ACC_LOCAL_DIR' in os.environ.keys():
    sys.path.append(os.environ['ACC_LOCAL_DIR']+'/tao/python/')
else:
    sys.path.append(os.environ['ACC_ROOT_DIR']+'/tao/python/')
from tao_pexpect.tao_pipe import tao_io
import pytao
import tkinter as tk

class new_stdout(object):
    '''
    Re-routes the print statements generated by tao_io
    so that they can be shown by tao_console.
    '''
    def __init__(self):
        self.file_obj = io.StringIO()
    def __enter__(self):
        self.current_out = sys.stdout
        sys.stdout = self.file_obj
        return self.file_obj
    def __exit__(self, type, value, traceback):
        sys.stdout = self.current_out

def filter_output(x):
    '''
    Filters out certain ANSI escape sequences from the string x
    '''
    if not isinstance(x, str):
        return x
    # Filter out \[[6 q first
    x = x.replace('\x1b[6 q', '')
    # replace line feed ('\x0a') with return ('\x0d')
    #while x.find('\x0a') != -1:
    #  x = x.replace('\x0a', '\x0d')
    # Remove xterm-specific escape code
    if x.find('\x1b[?1034h') != -1:
        x = x.replace('\x1b[?1034h', "")
    # Filter out color codes
    color_regex = re.compile('\x1b\\[[0-9;]*m')
    matches = color_regex.findall(x)
    for color in matches:
        x = x.replace(color, '')
    return x


class tao_interface():
    '''
    Provides an interface between the GUI and
    the Tao command line
    '''
    def __init__(self, mode, init_args = "", tao_exe =  "", expect_str = "Tao>", so_lib=""):
        # DEBUG
        self.debug = False # set true to print debug messages
        # Put patterns of interest here
        self.debug_patterns = ['python plot_manage']
        if self.debug:
            print(init_args)
        ###
        self.mode = mode
        self.exe_lib_warnings = ""
        self.exe_lib_warning_type = 'normal'
        if 'ACC_LOCAL_ROOT' in os.environ.keys():
            EXE_DIR = os.environ['ACC_LOCAL_ROOT'] + '/production/bin/'
            LIB_DIR = os.environ['ACC_LOCAL_ROOT'] + '/production/lib/'
        else:
            EXE_DIR = os.environ['ACC_EXE'] + '/'
            LIB_DIR = None
        # Check for executable
        if os.path.isfile(tao_exe) and os.access(tao_exe, os.X_OK):
            exe_found = True
        elif os.path.isfile(EXE_DIR + 'tao') and os.access(EXE_DIR + 'tao', os.X_OK):
            tao_exe = EXE_DIR + 'tao'
            exe_found = True
            if (mode == "pexpect") & (tao_exe != ""):
                self.exe_lib_warnings += "Note: could not find " + tao_exe
                self.exe_lib_warnings += ".\nDefaulting to " + EXE_DIR + 'tao'
        else:
            exe_found = False
            if mode == "pexpect":
                self.exe_lib_warnings += "Warning: no executable found, defaulting to ctypes"
                self.exe_lib_warning_type = 'error'

        # Check for shared library (and set up self.ctypes_pipe)
        lib_found = False
        try:
            self.ctypes_pipe = pytao.Tao(so_lib=so_lib)
            lib_found = True
        except OSError: #so_lib not found
            if LIB_DIR != None:
                try:
                    self.ctypes_pipe = pytao.Tao(so_lib=LIB_DIR+'libtao.so')
                    lib_found = True
                    if mode == "ctypes":
                        self.exe_lib_warnings += "Note: could not find " + so_lib
                        self.exe_lib_warnings += ".\nUsing library in " + LIB_DIR
                except OSError: #so_lib not found
                    pass # will continue below
            if not lib_found:
                try:
                    self.ctypes_pipe = pytao.Tao(so_lib="")
                    lib_found = True
                    if mode == "ctypes":
                        self.exe_lib_warnings += "Note: could not find " + so_lib
                        self.exe_lib_warnings += ".\nUsing library in " + os.environ['ACC_ROOT_DIR']+'/production/lib/'
                except ValueError:
                    lib_found = False
                    if mode == "ctypes":
                        self.exe_lib_warnings += "Warning: no shared library found, defaulting to pexpect"
                        self.exe_lib_warning_type = 'error'
        except ValueError:
            lib_found = False

        if self.exe_lib_warnings != "":
            self.exe_lib_warnings += '\n'

        # Switch mode if necessary
        if exe_found and not lib_found:
            mode = 'pexpect'
            self.mode = 'pexpect'
        elif not exe_found and lib_found:
            mode = 'ctypes'
            self.mode = 'ctypes'
        elif not exe_found and not lib_found:
            mode = 'failed'
            self.mode='failed'

        # new_stdout() needed to capture print statements from tao_io
        with new_stdout() as output:
            if mode == "pexpect":
                self.pexpect_pipe = tao_io(init_args=init_args,
                        tao_exe=tao_exe, expect_str=expect_str)
            if mode == "ctypes":
                for line in self.ctypes_pipe.init(init_args):
                    print(line)
            if mode == 'failed':
                self.exe_lib_warnings += "FATAL: could not locate Tao shared library or executable.\n"
                self.exe_lib_warnings += "Please reinitialize with a good executable or shared library."
                self.exe_lib_warning_type = "fatal"
                print("")

        # Process startup message
        output = output.getvalue()
        output = filter_output(output)
        self.startup_message = output

        self.message = ""
        self.message_type = "" #conveys color info to console
        self.printed = tk.BooleanVar()
        self.printed.set(False)
        # DEV PURPOSES ONLY
        self._root = self.printed._root

    def cmd_in(self, cmd_str, no_warn=False):
        '''
        Runs cmd_str at the Tao command line and returns the output
        Warning messages generated by this command are suppressed when
        no_warn is set True
        '''
        # DEBUG
        if self.debug:
            match = False
            if self.debug_patterns == 'All':
                match = True
            elif isinstance(self.debug_patterns, list):
                for p in self.debug_patterns:
                    if cmd_str.find(p) == 0:
                        match = True
            if match:
                current_time = time.localtime()
                y = str(current_time.tm_year)
                mo = str(current_time.tm_mon)
                if len(mo) == 1:
                    mo = '0' + mo
                day = str(current_time.tm_mday)
                if len(day) == 1:
                    day = '0' + day
                hr = str(current_time.tm_hour)
                if len(hr) == 1:
                    hr = '0' + hr
                mn = str(current_time.tm_min)
                if len(mn) == 1:
                    mn = '0' + mn
                sec = str(current_time.tm_sec)
                if len(sec) == 1:
                    sec = '0' + sec
                print(y+'-'+mo+'-'+day+' '+hr+':'+mn+':'+sec, cmd_str)
        if cmd_str.find("dev ") ==0:
            cmd_str = cmd_str[4:]
            with new_stdout() as output:
                exec(cmd_str)
            output = output.getvalue()
            output = filter_output(output)
            return output
        ###
        self.message = ""
        self.message_type = "normal" #conveys color info to console
        if cmd_str.find("single_mode") == 0:
            output = "single_mode not supported on the GUI command line"
            self.message_type = "error"
        elif self.mode=="pexpect":
            output = self.pexpect_pipe.cmd_in(cmd_str)
        elif self.mode=='ctypes':
            output_list = self.ctypes_pipe.cmd(cmd_str)
            output = ""
            for line in output_list:
                if line.strip != '':
                    output += line + '\n'
            if (len(output) > 0) and (output[-1] == '\n'):
                output = output[:-1]
        else:
            output = ""
        # Scrub output for extra new lines at the end,
        # as well as escape characters
        if cmd_str.find('python') == 0:
            output = output.replace('\r\n\r\n', '')
        output = filter_output(output)
        #if no_warn:
        #  return output
        if cmd_str.find("spawn ") == 0:
            self.message += "WARNING: the spawn command is very dangerous "
            self.message += "and may cause the GUI to hang if the spawned "
            self.message += "process does not exit quickly."
            self.message_type = "error"
            self.printed.set(True)
            self.message = ""
            self.message_type = "normal"
        if output.find("[ERROR") != -1:
            self.message += "Warning: Error occurred in Tao\n"
            self.message += "The offending command: " + cmd_str + "\n"
            self.message += "The error (first 20 lines):\n"
            if len(output.splitlines()) > 20:
                for i in range(20):
                    self.message += (output.splitlines()[i]) + "\n"
            else:
                self.message += output
            self.message_type = "error"
            if not no_warn:
                self.printed.set(True)
        if (output.find("Backtrace") != -1) | \
                (output.find("SIGSEGV") != -1):
            self.message = "Error occurred in Tao, causing it to crash\n"
            self.message += "The offending command: " + cmd_str + '\n'
            self.message += "The error:\n"
            self.message += output + '\n'
            self.message_type = "fatal"
            if not no_warn:
                self.printed.set(True)
        return output

    def cmd(self, cmd_str):
        '''
        Runs cmd_str at the Tao command line and prints the output
        '''
        output = self.cmd_in(cmd_str, no_warn=True)
        self.message_type = "normal"
        self.message = output
        self.printed.set(True)