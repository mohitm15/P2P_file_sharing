#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Dimitrios Paraschas
# 1562
# Dimitrios Greasidis
# 1624
# Stefanos Papanastasiou
# 1608


from __future__ import print_function
import logging
import os
import signal
import socket
import sys
import Queue
from threading import Thread

from library.library import json_load
from library.library import json_save
from library.library import send_message


DEBUG = True
#DEBUG = False


configuration_file = ""
configuration = {}
share_directory = ""
full_list_of_files = []
requested_file = ""

# handle ctrl-c signal
def sigint_handler(signal, frame):
    # cli_output
    print()
    logging.info("CTRL-C received, exiting")
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)

# main recursive function used communication (client-server)
def converse(server, incoming_buffer, own_previous_command):
    global configuration
    global full_list_of_files
    global requested_file

# parse message
    if "\0" not in incoming_buffer:
        incoming_buffer += server.recv(4096)
        return converse(server, incoming_buffer, own_previous_command)
    else:
        index = incoming_buffer.index("\0")
        message = incoming_buffer[0:index-1]
        incoming_buffer = incoming_buffer[index+1:]

    logging.info("message received: " + message)

    lines = message.split("\n")
    fields = lines[0].split()
    command = fields[0]

# protocol messages and answers
    if command == "AVAILABLE":
        username = fields[1]
        username = get_name(username)

        send_message(server, "IWANT " + username + "\n\0")

        return converse(server, incoming_buffer, "IWANT")

    elif command == "WELCOME":
        username = fields[1]
        configuration["username"] = username
        json_save(configuration_file, configuration)

        return None, incoming_buffer

    elif command == "FULLLIST" and own_previous_command == "SENDLIST":
        number_of_files = int(fields[1])

        if number_of_files != (len(lines) - 1):
            logging.warning("invalid FULLLIST message, wrong number of files")
            send_message(server, "ERROR\n\0")
            sys.exit(-1)
        else:
            full_list_of_files = lines[1:]

            # cli_output
            print()
            print("full list of clients' files")
            for line in lines[1:]:
                print(line)

        return None, incoming_buffer

    elif command == "AT" and own_previous_command =="WHERE":
        peer_ip = fields[1]
        peer_port = int(fields[2])

        return (peer_ip, peer_port), incoming_buffer

    elif command == "OK" and own_previous_command in ("LIST", "LISTENING"):
        return None, incoming_buffer

    elif command == "ERROR":
        logging.warning("ERROR message received, exiting")
        sys.exit(-1)

    else:
        # TODO
        # handle invalid commands
        logging.warning('an invalid command was received: "{}"'.format(command))
        sys.exit(-1)

# make the sockets and establish the connection
def connection_init(address):
    ip, port = address

    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error:
        logging.error("socket.socket error")
        sys.exit(-1)

    # TODO
    # replace with the equivalent code without using an offset
    while True:
        try:
            connection.connect( (ip, port) )
            # cli_output
            logging.info("connected to server or peer {}:{}".format(ip, port))
            break
        except socket.error:
            # TODO
            # this will be an error in production, i.e. the port must be specific
            logging.debug("failed to connect to port {}, trying the next one".format(port))
            port += 1

    return connection

# get username from the user
def get_name(username_):
    # cli_output
    print('Specify a username (press enter for the default "{}"): '.format(username_))
    username = raw_input()

    if username == "":
        username = username_

    return username

# peer to peer connection with anorther client 
def peer_function(connection, address):
    """
    connection : connection socket
    address : (IP_address, port)
    """
    global share_directory

    incoming_buffer = ""

    while True:
		# parse message received
        while "\0" not in incoming_buffer:
            incoming_buffer += connection.recv(4096)

        index = incoming_buffer.index("\0")
        message = incoming_buffer[0:index-1]
        incoming_buffer = incoming_buffer[index+1:]

        logging.info("message received: " + message)

        fields = message.split()
        command = fields[0]
		# reveive protocol messsages and answer
        if command == "GIVE":
            file_ = share_directory + "/" + fields[1]

            if os.path.isfile(file_):
                # get the file size
                file_size = os.path.getsize(file_)

                send_message(connection, "TAKE {}\n\0".format(str(file_size)))

                file__ = open(file_, "rb")

                file_buffer = ""
                file_buffer = file__.read(1024)
                while file_buffer:
                    print("sending: " + file_buffer)
                    connection.send(file_buffer)
                    file_buffer = file__.read(1024)

                # cli_output
                logging.info("file {} sent".format(file_))

                file__.close()
            else:
                send_message(connection, "ERROR")
                connection.close()
                break

        elif command == "THANKS":
            connection.close()
            break

        else:
            send_message(connection, "ERROR")
            connection.close()
            break

    return

#make the socket and establish listening connection 
def listen(listening_ip, listening_port, queue):
    try:
        listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error:
        logging.error("socket.socket error")
        sys.exit(-1)

    try:
        listening_socket.bind( (listening_ip, listening_port) )
    except socket.error:
        logging.error("port {} in use, exiting".format(port))
        sys.exit(-1)

    # listen for incoming connections
    listening_socket.listen(5)

    # cli_output
    logging.info("client listening on {}:{}".format(listening_ip, str(listening_port)))

    listening_port = listening_socket.getsockname()[1]

    # pass the listening_ip and listening_port to the main thread
    queue.put( (listening_ip, listening_port) )

    # handle incoming peer connections
    peer_counter = 0
    while True:
        connection, address = listening_socket.accept()
        # cli_output
        logging.info("a peer connected from {}:{}".format(address[0], str(address[1])))

        peer_thread = Thread(name="peer {}".format(peer_counter),
                target=peer_function, args=(connection, address))
        # TODO
        # handle differently, terminate gracefully
        peer_thread.daemon = True
        peer_thread.start()

        peer_counter += 1

# function for the "TAKE" message
def give_me(peer):
    global requested_file

    # cli_output
    print()
    print("file name:")
    requested_file = raw_input()

    send_message(peer, "GIVE {}\n\0".format(requested_file))

    incoming_buffer = ""
	# parse message and answer
    while "\0" not in incoming_buffer:
        incoming_buffer += peer.recv(4096)

    index = incoming_buffer.index("\0")
    message = incoming_buffer[0:index-1]
    incoming_buffer = incoming_buffer[index+1:]

    logging.info("message received: " + message)

    fields = message.split()
    command = fields[0]
	# reveive protocol messsages and answer
    if command == "TAKE":
        file_size = fields[1]

        # get the file
        while len(incoming_buffer) < int(file_size):
            incoming_buffer += peer.recv(4096)
            logging.debug("received: " + incoming_buffer)
            # TODO
            # save the file chunk by chunk

        file_to_save = open(share_directory + "/" + requested_file, "wb")
        file_to_save.write(incoming_buffer)
        file_to_save.close()

        logging.info("file {} received".format(file_to_save))
        send_message(peer, "THANKS\n\0")
        peer.close()

    elif command == "NOTEXIST":
        return

    else:
        # TODO
        # handle invalid commands
        logging.warning('an invalid command was received: "{}"'.format(command))
        sys.exit(-1)


def main():
    global configuration
    global configuration_file
    global full_list_of_files
    global share_directory
# DEBUF messages
    logging.basicConfig(level=logging.DEBUG,
            format="[%(levelname)s] (%(threadName)s) %(message)s",
            filename="client.log",
            filemode="w")
    console = logging.StreamHandler()
    if DEBUG:
        console.setLevel(logging.DEBUG)
    else:
        console.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(levelname)s] (%(threadName)s) %(message)s")
    console.setFormatter(formatter)
    logging.getLogger("").addHandler(console)

# we use a .json file to save configurations
    configuration_file = "configuration.json"
# load file
    if os.path.isfile(configuration_file):
        configuration = json_load(configuration_file)
    else:
#
        configuration["server_host"] = "localhost"
        configuration["server_port"] = 45000
        configuration["listening_ip"] = "localhost"
        configuration["listening_port"] = 0
        configuration["share_directory"] = "share"
        json_save(configuration_file, configuration)

    logging.debug("configuration: " + str(configuration))

    share_directory = configuration["share_directory"]
    files_list = [ file_ for file_ in os.listdir(share_directory) if os.path.isfile(os.path.join(share_directory, file_)) ]

    logging.debug("files_list: " + str(files_list))

    server_address = (configuration["server_host"], configuration["server_port"])
    server = connection_init(server_address)


    # start with an empty incoming message buffer
    incoming_buffer = ""


    # send HELLO command
    ############################################################################
    if "username" in configuration:
        send_message(server, "HELLO " + configuration["username"] + "\n\0")
    else:
        send_message(server, "HELLO\n\0")

    unneeded, incoming_buffer = converse(server, incoming_buffer, "HELLO")


    # send LISTENING command
    ############################################################################
    listening_ip = configuration["listening_ip"]
    listening_port = configuration["listening_port"]

    queue = Queue.Queue()

    # spawn listening thread
    listening_thread = Thread(name="ListeningThread", target=listen,
            args=(listening_ip, listening_port, queue))
    # TODO
    # handle differently, terminate gracefully
    listening_thread.daemon = True
    listening_thread.start()

    listening_ip, listening_port = queue.get()

    listening_message = "LISTENING {} {}\n\0".format(listening_ip, listening_port)
    send_message(server, listening_message)

    converse(server, incoming_buffer, "LISTENING")


    # send LIST command
    ############################################################################
    list_message = "LIST {}\n".format(len(files_list))
    for file_ in files_list:
        list_message += file_ + "\n"
    list_message += "\0"
    send_message(server, list_message)

    converse(server, incoming_buffer, "LIST")


     # send SENDLIST command
    ############################################################################
    send_message(server, "SENDLIST " + "\n\0")

    converse(server, incoming_buffer, "SENDLIST")


    # options menu/loop
    ############################################################################
    while True:
        print()
        print("options:")
        print("1: SENDLIST / s : request the list of clients and shared files")
        print("2: WHERE / w : request the IP address and port of the specified client")
        print("5: QUIT / q : exit the program")

        option = raw_input()
        if option in ["1", "s", "S", "sendlist", "SENDLIST"]:
            send_message(server, "SENDLIST " + "\n\0")

            converse(server, incoming_buffer, "SENDLIST")

        elif option in ["2", "w", "W", "where", "WHERE"]:
            print("Enter the username of the client:")

            while True:
                client = raw_input()

                if client == configuration["username"]:
                    print("{} is you, try again: ".format(client))
                    continue

                if client in [pair.split()[0] for pair in full_list_of_files]:
                    break

                print("{} is an invalid client username, try again: ".format(client))

            send_message(server, "WHERE " + client + "\n\0")

            (peer_ip, peer_port), incoming_buffer = converse(server, incoming_buffer, "WHERE")

            peer = connection_init( (peer_ip, peer_port) )

            give_me(peer)

        elif option in ["5", "q", "Q", "quit", "QUIT"]:
            sys.exit(0)

        else:
            print("invalid option, try again")


if __name__ == "__main__":
    main()
