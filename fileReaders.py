import sys
import os
import datetime
import calendar
import csv
from copy import copy
import locale
from bisect import bisect_left
import pandas as pd

os.chdir("/media/OS/Users/Nash Taylor/Documents/My Documents/School/Machine Learning Nanodegree/Capstone")
locale.setlocale(locale.LC_NUMERIC, 'en_US.utf8')

cardNumRangeT = [str(i) for i in range(2,10)] + ['T','J','Q','K','A']
cardNumRange10 = [str(i) for i in range(2,11)] + ['J','Q','K','A']
cardSuitRange = ['d','c','h','s']
deckT = [str(i) + str(j) for i in cardNumRangeT for j in cardSuitRange]
deck10 = [str(i) + str(j) for i in cardNumRange10 for j in cardSuitRange]

errors = []

def toFloat(s):
    if len(s)>=3 and s[-3]==',':
        s[-3] = '.'
    return locale.atof(s)

def readABSfile(filename):
    # HANDS INFORMATION
    with open(filename,'r') as f:
        startString = "Stage #"
        fileContents = [startString + theRest for theRest in f.read().replace('\r','').split(startString)]
        fileContents = fileContents[1:]
    
    
    data = []
    lineToRead = True
    src = "abs"
    
    for i,hand in enumerate(fileContents):
        try:
            ###################### HAND INFORMATION ###########################
            # add small and big blinds
            fn = filename[filename.find("rawdata")+8:]
            bb = float(fn[:fn.find("/")])
            if bb==0.25:
                sb = 0.1
            else:
                sb = bb/2
            # add date
            dateStart = hand.find("-") + 2
            dateEnd = dateStart + 10
            dateStr = hand[dateStart:dateEnd]
            dateObj = datetime.datetime.strptime(dateStr, '%Y-%m-%d').date()
            # add time
            timeStart = dateEnd + 1
            timeEnd = timeStart + 8
            timeStr = hand[timeStart:timeEnd]
            timeObj = datetime.datetime.strptime(timeStr, '%H:%M:%S').time()
            # add table
            tableStart = hand.find("\n") + 8
            tableEnd = tableStart + hand[tableStart:].find("(") - 1
            table = hand[tableStart:tableEnd]
            # add dealer
            dealerStart = hand.find("Seat #") + 6
            dealerEnd = dealerStart + hand[dealerStart:].find(" ")
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            i = 2
            while lines[i][:5]=="Seat ":
                numPlayers += 1
                i += 1
            # add board
            boardLine = lines[lines.index("*** SUMMARY ***") + 2]
            if boardLine[:5]=="Board":
                board = boardLine[7:-1].split()
            else:
                board = []
    
            ####################### PLAYER INFORMATION ########################
            
            # initialize...
            cp = 0
            cb = 0
            npl = 0
            rd = "Preflop"
            seats = {}
            startStacks = {}
            stacks = {}
            holeCards = {}
            roundInvestments = {}
            lenBoard = 0
            
            # go through lines to populate seats
            n = 2
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find("-")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:(line.find("-")-1)].strip()))
                startStacks[player] = toFloat(line[(line.find("(")+2):(line.find("in chips")-1)])
                assert startStacks[player]!=0
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                roundInvestments[player] = 0
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)
            
            # go through again to collect hole card info
            for line in lines:
                maybePlayerName = line[:line.find(" ")]
                if maybePlayerName in seats.keys() and line.find("Shows")>=0:
                    hc = line[(line.find("[")+1):line.find("]")]
                    hc = hc.split()
                    holeCards[maybePlayerName] = hc
            
            for line in lines:
                # skip SUMMARY section by changing lineToRead when encounter it
                # stop skipping once encounter "Stage"
                if line.find("Stage")>=0:
                    lineToRead = True
                elif line=="*** SUMMARY ***":
                    lineToRead = False
            
                if lineToRead:
                    newRow = {}
                    maybePlayerName = line[:line.find(" ")]
                    
                    if line[:5]=="Stage":
                        stage = src + "-" + line[(line.find("#")+1):line.find(":")]
                       
                    elif line[:3]=="***":
                        for key in roundInvestments:
                            roundInvestments[key] = 0
                        rdStart = line.find(" ")+1
                        rdEnd = rdStart + line[rdStart:].find("*") - 1
                        rd = line[rdStart:rdEnd].title().strip()
                        if rd!='Pocket Cards':
                            cb = 0
                        if rd=='Flop':
                            lenBoard = 3
                        elif rd=='Turn':
                            lenBoard = 4
                        elif rd=='River':
                            lenBoard = 5
                        elif rd.find("Card")>=0:
                            rd = 'Preflop'
                        elif rd=='Show Down':
                            continue
                        else:
                            raise ValueError
                    
                    # create new row IF row is an action (starts with encrypted player name)
                    elif maybePlayerName in seats.keys():
                        seat = seats[maybePlayerName]
                        fullA = line[(line.find("-") + 2):].strip()
                        isAllIn = fullA.find("All-In")>=0
                        if fullA.find("Posts")>=0:
                            if fullA.find('dead')>=0:
                                a = 'deadblind'
                                amt = toFloat(fullA[fullA.find("$")+1:])
                            else:
                                a = 'blind'
                                amt = toFloat(fullA[fullA.find("$")+1:])
                            cp += amt
                            roundInvestments[maybePlayerName] += amt
                            oldCB = copy(cb)
                            cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA=="Folds":
                            a = 'fold'
                            amt = 0.
                            npl -= 1
                            oldCB = copy(cb)
                        elif fullA.find('Checks')>=0:
                            a = 'check'
                            amt = 0.
                            oldCB = copy(cb)
                        elif fullA.find("Bets")>=0:
                            a = 'bet'
                            amt = toFloat(fullA[(fullA.find("$")+1):])
                            cp += amt
                            roundInvestments[maybePlayerName] += amt
                            oldCB = copy(cb)
                            cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA.find('Raises')>=0:
                            a = 'raise'
                            amt = toFloat(fullA[(fullA.find('to')+4):])
                            roundInvestments[maybePlayerName] = amt
                            cp += amt
                            oldCB = copy(cb)
                            cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA.find('Calls')>=0:
                            a = 'call'
                            amt = toFloat(fullA[(fullA.find('$')+1):])
                            roundInvestments[maybePlayerName] += amt
                            cp += amt
                            stacks[maybePlayerName] -= amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                        elif isAllIn:
                            revFullA = fullA[::-1]
                            amt = toFloat(revFullA[:revFullA.find('$')][::-1])
                            if cb==0:
                                a = 'bet'
                                roundInvestments[maybePlayerName] += amt
                            elif amt > cb:
                                a = 'raise'
                                roundInvestments[maybePlayerName] = amt
                            else:
                                a = 'call'
                                roundInvestments[maybePlayerName] += amt
                            cp += amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                            stacks[maybePlayerName] -= amt
                        else:
                            continue
                        if oldCB > (roundInvestments[maybePlayerName] - amt):
                            assert a!='bet'
                        else:
                            assert a!='call'
                        # consistent formatting for round
                        newRow = {'GameNum':stage,
                                  'SeatNum':seat,
                                  'Round':rd,
                                  'Player':maybePlayerName,
                                  'StartStack':startStacks[maybePlayerName],
                                  'CurrentStack':stacks[maybePlayerName] + amt,
                                  'Action':a,
                                  'Amount':amt,
                                  'AllIn':isAllIn,
                                  'CurrentBet':oldCB,
                                  'CurrentPot':cp-amt,
                                  'NumPlayersLeft':npl+1 if a=='fold' else npl,
                                  'Date': dateObj,
                                  'Time': timeObj,
                                  'SmallBlind': sb,
                                  'BigBlind': bb,
                                  'Table': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt
                                  }
                        for ii in [1,2]:
                            c = holeCards[maybePlayerName][ii-1]
                            if c is not None:
                                newRow['HoleCard'+str(ii)] = deck10.index(c)
                        for ii in range(1,lenBoard+1):
                            newRow["Board"+str(ii)] = deck10.index(board[ii-1])
                        data.append(newRow)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            global errors
            errors.append(dict(
                zip(('file','src','hand#','type','value','traceback'),
                    [filename, src, i] + list(sys.exc_info()))))
    
    return data
                
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################

def readFTPfile(filename):
    with open(filename,'r') as f:
        startString = "Full Tilt Poker Game #"
        fileContents = [startString + theRest for theRest in f.read().replace('\r','').split(startString)]
        fileContents = fileContents[1:]
        
    
    data = []
    lineToRead = True
    src = "ftp"
    
    for i,hand in enumerate(fileContents):
        try:
            ####################### HAND INFORMATION ##############################
            if hand.find('canceled')==-1:
                # add small and big blinds
                fn = filename[filename.find("rawdata")+8:]
                bb = float(fn[:fn.find("/")])
                if bb==0.25:
                    sb = 0.1
                else:
                    sb = bb/2
                # add date
                dateEnd = hand.find("\n")
                dateStart = dateEnd - 10
                dateStr = hand[dateStart:dateEnd]
                dateObj = datetime.datetime.strptime(dateStr, '%Y/%m/%d').date()
                # add time
                timeEnd = dateStart - 6
                timeStart = timeEnd - 8
                timeStr = hand[timeStart:timeEnd].strip()
                timeObj = datetime.datetime.strptime(timeStr, '%H:%M:%S').time()
                # add table
                tableStart = hand.find("Table") + 6
                tableEnd = tableStart + hand[tableStart:].find(" ")
                table = hand[tableStart:tableEnd]
                # add dealer
                dealerStart = hand.find("seat #") + 6
                dealerEnd = dealerStart + hand[dealerStart:].find("\n")
                dealer = int(hand[dealerStart:dealerEnd])
                # add numPlayers
                lines = [s.rstrip() for s in hand.split('\n')]
                numPlayers = 0
                i = 1
                while lines[i][:5]=="Seat ":
                    if lines[i].find("sitting out")==-1:
                        numPlayers += 1
                    i += 1
                # add board
                boardLine = lines[lines.index("*** SUMMARY ***") + 2]
                if boardLine[:5]=="Board":
                    board = boardLine[8:-1].split()
                else:
                    board = []
            
            ########################## PLAYER INFORMATION #########################
                
                cp = 0
                cb = 0
                npl = 0
                rd = "Preflop"
                seats = {}
                startStacks = {}
                stacks = {}
                holeCards = {}
                roundInvestments = {}
                lenBoard = 0
                
                # go through lines to populate seats
                n = 1
                seatnum = 1
                seatnums = []
                while lines[n][:4]=="Seat":
                    line = lines[n]
                    playerStart = line.find(":")+2
                    playerEnd = playerStart + line[playerStart:].find(' ')
                    player = line[playerStart:playerEnd]
                    seats[player] = seatnum
                    seatnum += 1
                    seatnums.append(int(line[5:line.find(":")]))
                    startStacks[player] = toFloat(line[(line.find("(")+2):line.find(")")])
                    assert startStacks[player]!=0
                    stacks[player] = startStacks[player]
                    holeCards[player] = [None, None]
                    roundInvestments[player] = 0
                    n += 1
                    npl += 1
                          
                # make dealer num relative to missing seats
                dealer = bisect_left(seatnums, dealer) % len(seatnums)

                # go through again to collect hole card info
                for line in lines:
                    maybePlayerName = line[:line.find(" ")]
                    if maybePlayerName in seats.keys() and line.find("shows [")>=0:
                        hc = line[(line.find("[")+1):line.find("]")]
                        hc = hc.split()
                        holeCards[maybePlayerName] = hc
                
                for line in lines:
                    # skip SUMMARY section by changing lineToRead when encounter it
                    # stop skipping once encounter "Stage" or "Game" or whatever
                    if line.find("Game")>=0:
                        lineToRead = True
                    elif line=="*** SUMMARY ***":
                        lineToRead = False
                
                    if lineToRead:
                        newRow = {}
                        maybePlayerName = line[:line.find(" ")]
                        seatnum = 1
                        
                        if line[:20]=="Full Tilt Poker Game":
                            stage = src + "-" + line[(line.find("#")+1):line.find(":")]
                            
                        elif line[:3]=="***":
                            for key in roundInvestments:
                                roundInvestments[key] = 0
                            rdStart = line.find(" ")+1
                            rdEnd = rdStart + line[rdStart:].find("*") - 1
                            rd = line[rdStart:rdEnd]
                            if rd!="HOLE CARDS":
                                cb = 0
                            rd = rd.title().strip()
                            if rd=='Flop':
                                lenBoard = 3
                            elif rd=='Turn':
                                lenBoard = 4
                            elif rd=='River':
                                lenBoard = 5
                            elif rd.find("Card")>=0:
                                rd = 'Preflop'
                            elif rd=='Show Down':
                                continue
                            else:
                                raise ValueError
                        
                        # create new row IF row is an action (starts with encrypted player name)
                        elif maybePlayerName in seats.keys():
                            seat = seats[maybePlayerName]
                            fullA = line[(line.find(" ") + 1):].strip()
                            isAllIn = fullA.find("all in")>=0
                            if fullA.find("posts")>=0:
                                if fullA.find('dead')>=0:
                                    a = 'deadblind'
                                    amt = toFloat(fullA[fullA.find("$")+1:])
                                else:
                                    a = 'blind'
                                    amt = toFloat(fullA[fullA.find("$")+1:])
                                cp += amt
                                roundInvestments[maybePlayerName] += amt
                                oldCB = copy(cb)
                                if cb<amt:
                                    cb = amt
                                stacks[maybePlayerName] -= amt
                            elif fullA=="folds":
                                a = 'fold'
                                amt = 0.
                                npl -= 1
                                seats.pop(maybePlayerName)
                                oldCB = copy(cb)
                            elif fullA.find('checks')>=0:
                                a = 'check'
                                amt = 0.
                                oldCB = copy(cb)
                            elif fullA.find("bets")>=0 and fullA.find("Uncalled")==-1:
                                a = 'bet'
                                if isAllIn or fullA.find(", ")>=0:
                                    amt = toFloat(fullA[(fullA.find('$')+1):fullA.find(", ")])
                                else:
                                    amt = toFloat(fullA[(fullA.find('$')+1):])
                                cp += amt
                                roundInvestments[maybePlayerName] += amt
                                oldCB = copy(cb)
                                cb = amt
                                stacks[maybePlayerName] -= amt
                            elif fullA.find('raises')>=0:
                                a = 'raise'
                                if isAllIn or fullA.find(", ")>=0:
                                    amt = toFloat(fullA[(fullA.find('$')+1):fullA.find(", ")])
                                else:
                                    amt = toFloat(fullA[(fullA.find('$')+1):])
                                roundInvestments[maybePlayerName] = amt
                                cp += amt
                                oldCB = copy(cb)
                                if cb<amt:
                                    cb = amt
                                stacks[maybePlayerName] -= amt
                            elif fullA.find('calls')>=0:
                                a = 'call'
                                if isAllIn or fullA.find(", ")>=0:
                                    amt = toFloat(fullA[(fullA.find('$')+1):fullA.find(", ")])
                                else:
                                    amt = toFloat(fullA[(fullA.find('$')+1):])
                                cp += amt
                                roundInvestments[maybePlayerName] += amt
                                stacks[maybePlayerName] -= amt
                                oldCB = copy(cb)
                                if cb<amt:
                                    cb = amt
                            elif fullA=='is sitting out':
                                numPlayers -= 1
                                npl -= 1
                                seats.pop(maybePlayerName)
                                continue
                            else:
                                continue
                            if oldCB > (roundInvestments[maybePlayerName] - amt):
                                assert a!='bet'
                            else:
                                assert a!='call'
                            newRow = {'GameNum':stage,
                                      'SeatNum':seat,
                                      'Round':rd,
                                      'Player':maybePlayerName,
                                      'StartStack':startStacks[maybePlayerName],
                                      'CurrentStack':stacks[maybePlayerName] + amt,
                                      'Action':a,
                                      'Amount':amt,
                                      'AllIn':isAllIn,
                                      'CurrentPot':cp-amt,
                                      'CurrentBet':oldCB,
                                      'NumPlayersLeft': npl+1 if a=='fold' else npl,
                                      'Date': dateObj,
                                      'Time': timeObj,
                                      'SmallBlind': sb,
                                      'BigBlind': bb,
                                      'Table': table.title(),
                                      'Dealer': dealer,
                                      'NumPlayers': numPlayers,
                                      'LenBoard': lenBoard,
                                      'InvestedThisRound': roundInvestments[maybePlayerName] - amt
                                      }
                            for ii in [1,2]:
                                c = holeCards[maybePlayerName][ii-1]
                                if c is not None:
                                    newRow['HoleCard'+str(ii)] = deckT.index(c)
                            for ii in range(1,lenBoard+1):
                                newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                            data.append(newRow)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            global errors
            errors.append(dict(
                zip(('file','src','hand#','type','value','traceback'),
                    [filename, src, i] + list(sys.exc_info()))))
            
    return data

###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################

def readONGfile(filename):
    with open(filename,'r') as f:
        startString = "***** History"
        fileContents = [startString + theRest for theRest in f.read().replace('\r','').split(startString)]
        fileContents = fileContents[1:]
    
    data = []
    lineToRead = True
    src = "ong"
    
    for i,hand in enumerate(fileContents):
        try:
            ####################### HAND INFORMATION ##############################
            # add small and big blinds
            fn = filename[filename.find("rawdata")+8:]
            bb = float(fn[:fn.find("/")])
            if bb==0.25:
                sb = 0.1
            else:
                sb = bb/2
            # add date
            monthStart = hand.find("Start hand:") + 16
            monthEnd = monthStart + 3
            dateStart = monthEnd + 1
            dateEnd = dateStart + 2
            yearStart = dateEnd + 19
            yearEnd = yearStart + 4
            monthConv = {v:k for k,v in enumerate(calendar.month_abbr)}
            dateObj = datetime.date(int(hand[yearStart:yearEnd]),
                                    int(monthConv[hand[monthStart:monthEnd]]),
                                    int(hand[dateStart:dateEnd]))
            # add time
            timeStart = dateEnd + 1
            timeEnd = timeStart + 8
            timeStr = hand[timeStart:timeEnd]
            timeObj = datetime.datetime.strptime(timeStr, '%H:%M:%S').time()
            # add table
            tableStart = hand.find("Table") + 7
            tableEnd = tableStart + hand[tableStart:].find(" ")
            table = hand[tableStart:tableEnd]
            # add dealer
            dealerStart = hand.find("Button:") + 13
            dealerEnd = dealerStart + hand[dealerStart:].find("\n")
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            i = 5
            while lines[i][:5]=="Seat ":
                if lines[i].find("sitting out")==-1:
                    numPlayers += 1
                i += 1
            # add board
            board = []
            flopStart = hand.find("Dealing flop")
            turnStart = hand.find("Dealing turn")
            riverStart = hand.find("Dealing river")
            if flopStart>=0:
                flopStart += 14
                flopEnd = flopStart + 10
                flop = hand[flopStart:flopEnd]
                board += flop.replace(',','').split()
            if turnStart>=0:
                turnStart += 14
                turnEnd = turnStart + 2
                turn = hand[turnStart:turnEnd]
                board.append(turn.replace(',',''))
            if riverStart>=0:
                riverStart += 15
                riverEnd = riverStart + 2
                river = hand[riverStart:riverEnd]
                board.append(river.replace(',',''))
            
            ########################## PLAYER INFORMATION #########################
            
            cp = 0
            cb = 0
            npl = 0
            rd = "Preflop"
            seats = {}
            startStacks = {}
            stacks = {}
            holeCards = {}
            roundInvestments = {}
            lenBoard = 0
            
            # go through lines to populate seats
            n = 5
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("(")+2):line.find(")")])
                assert startStacks[player]!=0
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                roundInvestments[player] = 0
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to collect hole card info
            cardLines = [l for l in lines if l.find(", [")>=0]
            for line in cardLines:
                maybePlayerName = line[(line.find(":")+2):(line.find("(")-1)]
                if line.find("[")>=0:
                    hc = line[(line.find("[")+1):-1]
                    hc = hc.split(", ")
                    holeCards[maybePlayerName] = hc
            
            for line in lines:
                # skip SUMMARY section by changing lineToRead when encounter it
                # stop skipping once encounter "Stage" or "Game" or whatever
                if line.find("History for hand")>=0:
                    lineToRead = True
                elif line=="Summary:":
                    lineToRead = False
            
                if lineToRead:
                    newRow = {}
                    maybePlayerName = line[:line.find(" ")]
                    
                    if line[:22]=="***** History for hand":
                        stage = src + "-" + line[24:(24 + line[24:].find("*") - 1)]
                        
                    elif line[:3]=="---" and len(line)>3:
                        for key in roundInvestments:
                            roundInvestments[key] = 0
                        rdStart = line.find("Dealing")+8
                        rdEnd = rdStart + line[rdStart:].find("[") - 1
                        rd = line[rdStart:rdEnd].title().strip()
                        if rd!='Pocket Cards':
                            cb = 0
                        if rd=='Flop':
                            lenBoard = 3
                        elif rd=='Turn':
                            lenBoard = 4
                        elif rd=='River':
                            lenBoard = 5
                        elif rd.find("Card")>=0:
                            rd = 'Preflop'
                        else:
                            raise ValueError
                    
                    # create new row IF row is an action (starts with encrypted player name)
                    elif maybePlayerName in seats.keys():
                        seat = seats[maybePlayerName]
                        fullA = line[(line.find(" ") + 1):].strip()
                        isAllIn = fullA.find("all in")>=0
                        if fullA.find("posts")>=0:
                            a = 'blind'
                            amt = toFloat(fullA[fullA.find("$")+1:-1])
                            roundInvestments[maybePlayerName] += amt
                            cp += amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA=="folds":
                            a = 'fold'
                            amt = 0.
                            npl -= 1
                            oldCB = copy(cb)
                        elif fullA=='checks':
                            a = 'check'
                            amt = 0.
                            oldCB = copy(cb)
                        elif fullA.find("bets")>=0:
                            a = 'bet'
                            amtStart = fullA.find("$")+1
                            if isAllIn:
                                amt = toFloat(fullA[amtStart:(amtStart + fullA[amtStart:].find(" "))])
                                if cb>0:
                                    a = 'raise'
                                    roundInvestments[maybePlayerName] = amt
                                else:
                                    roundInvestments[maybePlayerName] += amt
                            else:
                                amt = toFloat(fullA[amtStart:])
                                roundInvestments[maybePlayerName] += amt
                            cp += amt
                            oldCB = copy(cb)
                            cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA.find('raises')>=0:
                            a = 'raise'
                            if isAllIn or fullA.find(", ")>=0:
                                amt = toFloat(fullA[(fullA.find('$')+1):fullA.find(", ")])
                            else:
                                amt = toFloat(fullA[(fullA.find('to')+4):])
                            roundInvestments[maybePlayerName] = amt
                            cp += amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA.find('calls')>=0:
                            a = 'call'
                            if isAllIn:
                                amt = toFloat(fullA[(fullA.find("$")+1):(fullA.find("[")-1)])
                            else:
                                amt = toFloat(fullA[(fullA.find('$')+1):])
                            roundInvestments[maybePlayerName] += amt
                            cp += amt
                            oldCB = copy(cb)
                            stacks[maybePlayerName] -= amt
                            if cb<amt:
                                cb = amt
                        else:
                            continue
                        if oldCB > (roundInvestments[maybePlayerName] - amt):
                            assert a!='bet'
                        else:
                            assert a!='call'
                        newRow = {'GameNum':stage,
                                  'SeatNum':seat,
                                  'Round':rd,
                                  'Player':maybePlayerName,
                                  'StartStack':startStacks[maybePlayerName],
                                  'CurrentStack':stacks[maybePlayerName] + amt,
                                  'Action':a,
                                  'Amount':amt,
                                  'AllIn':isAllIn,
                                  'CurrentPot':cp-amt,
                                  'CurrentBet':oldCB,
                                  'NumPlayersLeft': npl+1 if a=='fold' else npl,
                                  'Date': dateObj,
                                  'Time': timeObj,
                                  'SmallBlind': sb,
                                  'BigBlind': bb,
                                  'Table': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt
                                  }
                        for ii in [1,2]:
                            c = holeCards[maybePlayerName][ii-1]
                            if c is not None:
                                newRow['HoleCard'+str(ii)] = deckT.index(c)
                        for ii in range(1,lenBoard+1):
                            newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                        data.append(newRow)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            global errors
            errors.append(dict(
                zip(('file','src','hand#','type','value','traceback'),
                    [filename, src, i] + list(sys.exc_info()))))
        
    return data

###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################

def readPSfile(filename):
    # HANDS TABLE
    with open(filename,'r') as f:
        startString = "PokerStars Game #"
        fileContents = [startString + theRest for theRest in f.read().replace('\r','').split(startString)]
        fileContents = fileContents[1:]
    
    data = []
    lineToRead = True
    
    src = "ps"
    
    for i,hand in enumerate(fileContents):
        try:
            ###################### HAND INFORMATION ###########################
            # add small and big blinds
            fn = filename[filename.find("rawdata")+8:]
            bb = float(fn[:fn.find("/")])
            if bb==0.25:
                sb = 0.1
            else:
                sb = bb/2
            # add date
            dateStart = hand.find("-") + 2
            dateEnd = dateStart + 10
            dateStr = hand[dateStart:dateEnd]
            dateObj = datetime.datetime.strptime(dateStr, '%Y/%m/%d').date()
            # add time
            timeStart = dateEnd + 1
            timeEnd = hand.find("ET\n")
            timeStr = hand[timeStart:timeEnd].strip()
            timeObj = datetime.datetime.strptime(timeStr, '%H:%M:%S').time()
            # add table
            tableStart = hand.find("Table") + 7
            tableEnd = tableStart + hand[tableStart:].find("'")
            table = hand[tableStart:tableEnd]
            # add dealer
            dealerEnd = hand.find("is the button") - 1
            dealerStart = tableEnd + hand[tableEnd:].find("#") + 1
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            i = 2
            while lines[i][:5]=="Seat ":
                numPlayers += 1
                i += 1
            # add board
            boardLine = lines[lines.index("*** SUMMARY ***") + 2]
            if boardLine[:5]=="Board":
                board = boardLine[7:-1].split()
            else:
                board = ''
    
            ####################### PLAYER INFORMATION ########################
            # initialize...
            cp = 0
            cb = 0
            npl = 0
            rd = "Preflop"
            seats = {}
            startStacks = {}
            stacks = {}
            holeCards = {}
            roundInvestments = {}
            lenBoard = 0
            
            # go through lines to populate seats
            n = 2
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat" and lines[n].find("button")==-1:
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find('(') - 1
                player = line[playerStart:playerEnd]
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("$")+1):line.find(" in chips")])
                assert startStacks[player]!=0
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                roundInvestments[player] = 0
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to collect hole card info
            for line in lines:
                maybePlayerName = line[:line.find(":")]
                if maybePlayerName in seats.keys() and line.find("shows")>=0:
                    hc = line[(line.find("[")+1):line.find("]")]
                    hc = hc.split()
                    holeCards[maybePlayerName] = hc
            
            for line in lines:
                # skip SUMMARY section by changing lineToRead when encounter it
                # stop skipping once encounter "Stage"
                if line.find("PokerStars Game")>=0:
                    lineToRead = True
                elif line=="*** SUMMARY ***":
                    lineToRead = False
            
                if lineToRead:
                    newRow = {}
                    maybePlayerName = line[:line.find(":")]
                    
                    if line[:15]=="PokerStars Game":
                        stage = src + "-" + line[(line.find("#")+1):line.find(":")]
                                                
                    elif line[:3]=="***":
                        for key in roundInvestments:
                            roundInvestments[key] = 0
                        rdStart = line.find(" ")+1
                        rdEnd = rdStart + line[rdStart:].find("*") - 1
                        rd = line[rdStart:rdEnd].title().strip()
                        if rd!='Hole Cards':
                            cb = 0
                        if rd=='Flop':
                            lenBoard = 3
                        elif rd=='Turn':
                            lenBoard = 4
                        elif rd=='River':
                            lenBoard = 5
                        elif rd.find("Card")>=0:
                            rd = 'Preflop'
                        elif rd=='Show Down':
                            lineToRead = False
                        else:
                            raise ValueError
                    
                    # create new row IF row is an action (starts with encrypted player name)
                    elif maybePlayerName in seats.keys():
                        seat = seats[maybePlayerName]
                        fullA = line[(line.find(":") + 2):].strip()
                        isAllIn = fullA.find("all-in")>=0
                        if fullA.find("posts")>=0:
                            a = 'blind'
                            if fullA.find('small & big')>=0:
                                amt = bb
                            else:
                                amt = toFloat(fullA[(fullA.find("$")+1):])
                            roundInvestments[maybePlayerName] += amt
                            cp += amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA=="folds":
                            a = 'fold'
                            amt = 0.
                            npl -= 1
                            oldCB = copy(cb)
                        elif fullA.find('checks')>=0:
                            a = 'check'
                            amt = 0.
                            oldCB = copy(cb)
                        elif fullA.find("bets")>=0:
                            a = 'bet'
                            if isAllIn:
                                amt = toFloat(fullA[(fullA.find("$")+1):(fullA.find("and is"))])
                            else:
                                amt = toFloat(fullA[(fullA.find("$")+1):])
                            roundInvestments[maybePlayerName] += amt
                            cp += amt
                            oldCB = copy(cb)
                            cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA.find('raises')>=0:
                            a = 'raise'
                            if isAllIn:
                                amt = toFloat(fullA[(fullA.find('to')+4):(fullA.find("and is")-1)])
                            else:
                                amt = toFloat(fullA[(fullA.find('to')+4):])
                            roundInvestments[maybePlayerName] = amt
                            cp += amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                            stacks[maybePlayerName] -= amt
                        elif fullA.find('calls')>=0:
                            a = 'call'
                            if isAllIn:
                                amt = toFloat(fullA[(fullA.find('$')+1):(fullA.find("and is")-1)])
                            else:
                                amt = toFloat(fullA[(fullA.find('$')+1):])
                            roundInvestments[maybePlayerName] += amt
                            cp += amt
                            stacks[maybePlayerName] -= amt
                            oldCB = copy(cb)
                            if cb<amt:
                                cb = amt
                        elif fullA=='is sitting out':
                            numPlayers -= 1
                            npl -= 1
                            seats.pop(maybePlayerName)
                            continue
                        else:
                            continue
                        if oldCB > (roundInvestments[maybePlayerName] - amt):
                            assert a!='bet'
                        else:
                            assert a!='call'
                        newRow = {'GameNum':stage,
                                  'SeatNum':seat,
                                  'Round':rd,
                                  'Player':maybePlayerName,
                                  'StartStack':startStacks[maybePlayerName],
                                  'CurrentStack':stacks[maybePlayerName] + amt,
                                  'Action':a,
                                  'Amount':amt,
                                  'AllIn':isAllIn,
                                  'CurrentBet':oldCB,
                                  'CurrentPot':cp-amt,
                                  'NumPlayersLeft':npl+1 if a=='fold' else npl,
                                  'Date': dateObj,
                                  'Time': timeObj,
                                  'SmallBlind': sb,
                                  'BigBlind': bb,
                                  'Table': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt
                                  }
                        for ii in [1,2]:
                            c = holeCards[maybePlayerName][ii-1]
                            if c is not None:
                                newRow['HoleCard'+str(ii)] = deckT.index(c)
                        for ii in range(1,lenBoard+1):
                            newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                        data.append(newRow)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            global errors
            errors.append(dict(
                zip(('file','src','hand#','type','value','traceback'),
                    [filename, src, i] + list(sys.exc_info()))))
        
    return data

###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################

def readPTYfile(filename):
    # HANDS TABLE
    with open(filename,'r') as f:
        startString = "Game #"
        fileContents = [startString + theRest for theRest in f.read().replace('\r','').split(startString)]
        fileContents = fileContents[1:]
    
    data = []
    
    src = "pty"
    
    for i,hand in enumerate(fileContents):
        try:
            # if lost connection, drop hand
            if hand.find('due to some reason')>=0:
                raise ValueError
            ###################### HAND INFORMATION ###########################
            # add small and big blinds
            fn = filename[filename.find("rawdata")+8:]
            bb = float(fn[:fn.find("/")])
            if bb==0.25:
                sb = 0.1
            else:
                sb = bb/2
            # add date
            dateStart = hand.find(",") + 2
            if bb==10:
                dateStart += hand[dateStart:].find(",") + 2
            dateEnd = dateStart + hand[dateStart:].find(",")
            month, dateNum = hand[dateStart:dateEnd].split()
            monthConv = {v:k for k,v in enumerate(calendar.month_name)}
            year = hand[(hand.find("Table") - 6):(hand.find("Table") - 2)]
            dateObj = datetime.date(int(year),
                                    int(monthConv[month]),
                                    int(dateNum))
            # add time
            timeStart = dateEnd + 2
            timeEnd = timeStart + 8
            timeStr = hand[timeStart:timeEnd]
            timeObj = datetime.datetime.strptime(timeStr, '%H:%M:%S').time()
            # add table
            tableStart = hand.find("Table") + 6
            tableEnd = tableStart + hand[tableStart:].find(" ")
            table = hand[tableStart:tableEnd]
            # add dealer
            dealerEnd = hand.find("is the button") - 1
            dealerStart = tableEnd + hand[tableEnd:].find("Seat ") + 5
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            npStart = hand.find("Total number of players : ") + 26
            npEnd = npStart + hand[npStart:].find('\n')
            numPlayers = int(hand[npStart:npEnd].strip())
            # add board
            board = []
            flopStart = hand.find("Dealing Flop")
            turnStart = hand.find("Dealing Turn")
            riverStart = hand.find("Dealing River")
            if flopStart>=0:
                flopStart += 18
                flopEnd = flopStart + 10
                flop = hand[flopStart:flopEnd]
                board += flop.replace(',','').split()
            if turnStart>=0:
                turnStart += 18
                turnEnd = turnStart + 2
                turn = hand[turnStart:turnEnd]
                board.append(turn.replace(',',''))
            if riverStart>=0:
                riverStart += 19
                riverEnd = riverStart + 2
                river = hand[riverStart:riverEnd]
                board.append(river.replace(',',''))
    
            ####################### PLAYER INFORMATION ########################
            lines = [s.rstrip() for s in hand.split('\n')]
            lines = [l for l in lines if len(l)>0]
            # initialize...
            cp = 0
            cb = 0
            npl = 0
            rd = "Preflop"
            seats = {}
            startStacks = {}
            stacks = {}
            holeCards = {}
            roundInvestments = {}
            lenBoard = 0
            
            # go through lines to populate seats
            n = 7
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("$")+1):(line.find("USD")-1)])
                assert startStacks[player]!=0
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                roundInvestments[player] = 0
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to collect hole card info
            for line in lines:
                maybePlayerName = line[:line.find(" ")]
                if maybePlayerName in seats.keys() and line.find("shows")>=0:
                    hc = line[(line.find("[")+2):(line.find("]")-1)]
                    hc = hc.split(", ")
                    holeCards[maybePlayerName] = hc
            
            for line in lines:
                # skip SUMMARY section by changing lineToRead when encounter it
                # stop skipping once encounter "Game"
                newRow = {}
                maybePlayerName = line[:line.find(" ")]
                
                if line[:6]=="Game #":
                    stage = src + "-" + line[(line.find("#")+1):line.find(" starts")]
                    
                elif line[:2]=="**" and line[:5]!="*****":
                    for key in roundInvestments:
                        roundInvestments[key] = 0
                    rdStart = line.find(" ")+9
                    rdEnd = rdStart + line[rdStart:].find("*") - 1
                    rd = line[rdStart:rdEnd].title().strip()
                    if rd!='Down Cards':
                        cb = 0
                    if rd=='Flop':
                        lenBoard = 3
                    elif rd=='Turn':
                        lenBoard = 4
                    elif rd=='River':
                        lenBoard = 5
                    elif rd.find("Card")>=0:
                        rd = 'Preflop'
                    else:
                        raise ValueError
                
                # create new row IF row is an action (starts with encrypted player name)
                elif maybePlayerName in seats.keys():
                    seat = seats[maybePlayerName]
                    fullA = line[(line.find(" ") + 1):].strip()
                    isAllIn = fullA.find("all-In")>=0
                    if fullA.find("posts")>=0:
                        if fullA.find('dead')>=0:
                            a = 'deadblind'
                            amt = bb
                        else:
                            a = 'blind'
                            amtStart = fullA.find("$") + 1
                            amtEnd = fullA.find("USD") - 1
                            amt = toFloat(fullA[amtStart:amtEnd])
                        roundInvestments[maybePlayerName] += amt
                        cp += amt
                        oldCB = copy(cb)
                        cb = amt
                        stacks[maybePlayerName] -= amt
                    elif fullA=="folds":
                        a = 'fold'
                        amt = 0.
                        npl -= 1
                        oldCB = copy(cb)
                    elif fullA.find('checks')>=0:
                        a = 'check'
                        amt = 0.
                        oldCB = copy(cb)
                    elif fullA.find("bets")>=0:
                        a = 'bet'
                        amt = toFloat(fullA[(fullA.find("$")+1):(fullA.find("USD")-1)])
                        roundInvestments[maybePlayerName] += amt
                        cp += amt
                        oldCB = copy(cb)
                        cb = amt
                        stacks[maybePlayerName] -= amt
                    elif fullA.find('raises')>=0:
                        a = 'raise'
                        amt = toFloat(fullA[(fullA.find('$')+1):(fullA.find("USD")-1)])
                        roundInvestments[maybePlayerName] = amt
                        cp += amt
                        oldCB = copy(cb)
                        cb = amt
                        stacks[maybePlayerName] -= amt
                    elif fullA.find('calls')>=0:
                        a = 'call'
                        amt = toFloat(fullA[(fullA.find('$')+1):(fullA.find("USD")-1)])
                        amt -= roundInvestments[maybePlayerName]
                        roundInvestments[maybePlayerName] += amt
                        cp += amt
                        oldCB = copy(cb)
                        if cb<amt:
                            cb = amt
                        stacks[maybePlayerName] -= amt
                    elif isAllIn:
                        amt = toFloat(fullA[(fullA.find('$')+1):(fullA.find("USD")-1)])
                        if cb==0:
                            a = 'bet'
                            roundInvestments[maybePlayerName] += amt
                        elif amt > cb:
                            a = 'raise'
                            roundInvestments[maybePlayerName] = amt
                        else:
                            a = 'call'
                            amt += roundInvestments[maybePlayerName]
                            roundInvestments[maybePlayerName] = amt
                        cp += amt
                        stacks[maybePlayerName] -= amt
                        oldCB = copy(cb)
                        if cb<amt:
                            cb = amt
                    elif fullA=='is sitting out':
                        numPlayers -= 1
                        npl -= 1
                        seats.pop(maybePlayerName)
                        continue
                    else:
                        continue
                    if oldCB > (roundInvestments[maybePlayerName] - amt):
                        assert a!='bet'
                    else:
                        assert a!='call'
                    newRow = {'GameNum':stage,
                              'SeatNum':seat,
                              'Round':rd,
                              'Player':maybePlayerName,
                              'StartStack':startStacks[maybePlayerName],
                              'CurrentStack':stacks[maybePlayerName] + amt,
                              'Action':a,
                              'Amount':amt,
                              'AllIn':isAllIn,
                              'CurrentBet':oldCB,
                              'CurrentPot':cp-amt,
                              'NumPlayersLeft':npl+1 if a=='fold' else npl,
                              'Date': dateObj,
                              'Time': timeObj,
                              'SmallBlind': sb,
                              'BigBlind': bb,
                              'Table': table.title(),
                              'Dealer': dealer,
                              'NumPlayers': numPlayers,
                              'LenBoard': lenBoard,
                              'InvestedThisRound': roundInvestments[maybePlayerName] - amt
                             }
                    for ii in [1,2]:
                        c = holeCards[maybePlayerName][ii-1]
                        if c is not None:
                            newRow['HoleCard'+str(ii)] = deckT.index(c)
                    for ii in range(1,lenBoard+1):
                        newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                    data.append(newRow)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            global errors
            errors.append(dict(
                zip(('file','src','hand#','type','value','traceback'),
                    [filename, src, i] + list(sys.exc_info()))))
        
    return data

######################## READ ONE FILE ########################################
    
def readFile(filename):
    # get dataframe from one of the source-specific functions
    bf = filename[::-1]
    src = bf[(bf.find("HLN")+3):bf.find("/")][::-1].strip()
    
    if src=="ipn":
        return []
    
    func = "read" + src.upper() + "file"
    full = eval(func+"('"+filename+"')")
        
    return full
        
####################### READ ALL FILES ########################################
folders = ["rawdata/"+fdr for fdr in os.listdir('rawdata')]
allFiles = [folder+"/"+f for folder in folders for f in os.listdir(folder)
            if f.find('ipn ')==-1]

keys = ['GameNum','Date','Time','SeatNum','Round','Player','StartStack',
        'CurrentStack','Action','Amount','AllIn','CurrentBet','CurrentPot','InvestedThisRound',
        'NumPlayersLeft','SmallBlind','BigBlind','Table','Dealer','NumPlayers',
        'LenBoard','HoleCard1','HoleCard2','Board1','Board2','Board3','Board4','Board5']

processedCount = 0
totalRows = 0
indRows = []

def chunks(l,n):
    for i in range(0, len(l), n):
        yield l[i:i+n]

def readAllFiles(files,n):
    global processedCount, totalRows
    startTime = datetime.datetime.now()
    for ii,chunk in enumerate(chunks(files, n)):
        dataWriteTo = "data/"+"poker"+str(ii)+".csv"
        with open(dataWriteTo, 'ab') as outputFile:
            outputFile.write(','.join(keys) + "\n")
            dictWriter = csv.DictWriter(outputFile, keys)
            for i,f in enumerate(chunk):
                df = readFile(f)
                dictWriter.writerows(df)
                processedCount += 1
                totalRows += len(df)
                indRows.append(len(df))
            outputFile.close()
    print datetime.datetime.now() - startTime

readAllFiles(allFiles, 100)

'''
import itertools
import random
srcs = ['abs','ftp','ong','ps','pty']
stks = ['0.5','0.25','1','2','4','6','10']
examples = []

for sr,st in itertools.product(srcs,stks):
    allMatches = [f for f in allFiles if f.find("/"+sr)>=0 and f.find("/"+st+"/")>=0]
    if allMatches:
        examples.append(random.choice(allMatches))

readAllFiles(examples, len(examples))
test = pd.read_csv('data/poker0.csv')
'''