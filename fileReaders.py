import os
import shutil
import datetime
import calendar
from copy import copy
import locale
from bisect import bisect_left
import codecs
import multiprocessing
import MySQLdb

locale.setlocale(locale.LC_NUMERIC, 'en_US.utf8')

cardNumRangeT = [str(i) for i in range(2,10)] + ['T','J','Q','K','A']
cardNumRange10 = [str(i) for i in range(2,11)] + ['J','Q','K','A']
cardSuitRange = ['d','c','h','s']
deckT = [str(i) + str(j) for i in cardNumRangeT for j in cardSuitRange]
deck10 = [str(i) + str(j) for i in cardNumRange10 for j in cardSuitRange]
actions = ['blind','deadblind','fold','check','call','bet','raise']

def toFloat(s):
    if len(s)>=3 and s[-3]==',':
        s[-3] = '.'
    return locale.atof(s)

# TODO: fix NumPlayers for games where someone is sitting out (same for all rows)

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
            assert len(table)<=22
            # add dealer
            dealerStart = hand.find("Seat #") + 6
            dealerEnd = dealerStart + hand[dealerStart:].find(" ")
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            j = 2
            while lines[j][:5]=="Seat ":
                numPlayers += 1
                j += 1
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
            isAllIn = False
            lastNewRoundLine = -1
            winnings = {}
            
            # go through lines to populate seats
            n = 2
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find("-")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                assert not '$' in player and not ')' in player, "bad player name"
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:(line.find("-")-1)].strip()))
                startStacks[player] = toFloat(line[(line.find("(")+2):(line.find("in chips")-1)])
                assert startStacks[player]!=0, "start stack of 0"
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                winnings[player] = 0.
                roundInvestments[player] = 0
                roundActionNum = 1
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)
            
            # go through again to...
            # collect hole card info, check for bad names, find winner
            for j,line in enumerate(lines):
                maybePlayerName = line[:line.find(" ")]
                if len(maybePlayerName)==22:
                    assert maybePlayerName in seats.keys()
                if maybePlayerName in seats.keys() and line.find("Shows")>=0:
                    hc = line[(line.find("[")+1):line.find("]")]
                    hc = hc.split()
                    holeCards[maybePlayerName] = hc
                elif 'Collects' in line:
                    amt = line[(line.find('$')+1):]
                    amt = float(amt[:amt.find(' ')])
                    winnings[maybePlayerName] += amt
            
            for j,line in enumerate(lines):
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
                        nar = j - lastNewRoundLine
                        lastNewRoundLine = j
                        for key in roundInvestments:
                            roundInvestments[key] = 0
                        rdStart = line.find(" ")+1
                        rdEnd = rdStart + line[rdStart:].find("*") - 1
                        rd = line[rdStart:rdEnd].title().strip()
                        if rd!='Pocket Cards':
                            if nar>1:
                                assert roundActionNum!=1, "round with one action"
                            roundActionNum = 1
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
                                amt = fullA[fullA.find("$")+1:]
                                amt = toFloat(amt[:amt.find(" ")])
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
                            assert a!='bet', "illegal action"
                        else:
                            assert a!='call', "illegal action"
                        # consistent formatting for round
                        newRow = {'GameNum':stage,
                                  'RoundActionNum':roundActionNum,
                                  'SeatNum':seat,
                                  'Round':rd,
                                  'Player':maybePlayerName,
                                  'StartStack':startStacks[maybePlayerName],
                                  'CurrentStack':stacks[maybePlayerName] + amt,
                                  'Action':a,
                                  'Amount':amt,
                                  'AllIn':int(isAllIn),
                                  'CurrentBet':oldCB,
                                  'CurrentPot':cp-amt,
                                  'NumPlayersLeft':npl+1 if a=='fold' else npl,
                                  'Date': dateObj,
                                  'Time': timeObj,
                                  'SmallBlind': sb,
                                  'BigBlind': bb,
                                  'TableName': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt,
                                  'Winnings': winnings[maybePlayerName]
                                  }
                        try:
                            for ii in [1,2]:
                                c = holeCards[maybePlayerName][ii-1]
                                if c is None:
                                    newRow['HoleCard'+str(ii)] = -1
                                else:
                                    newRow['HoleCard'+str(ii)] = deckT.index(c)
                            for ii in range(1,lenBoard+1):
                                newRow["Board"+str(ii)] = deck10.index(board[ii-1])
                            for ii in range(lenBoard+1,6):
                                newRow["Board"+str(ii)] = -1
                        except ValueError:
                            pass
                        data.append(newRow)
                        roundActionNum += 1
            if data[-1]['RoundActionNum']==1:
                data.pop()
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            pass
    
    return data
                
###############################################################################
###############################################################################
###############################################################################
###############################################################################
###############################################################################

def readFTPfile(filename):    
    with codecs.open(filename, encoding='utf-8') as f:
        startString = "Full Tilt Poker Game #"
        fileContents = [startString + theRest for theRest in f.read().replace('\r','').split(startString)]
        fileContents = fileContents[1:]
    
    data = []
    lineToRead = True
    src = "ftp"
    
    for i,hand in enumerate(fileContents):
        try:
            assert not "@" in hand and not "\x16" in hand, "corrupted data"
            ####################### HAND INFORMATION ##############################
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
            assert len(table)<=22
            # add dealer
            dealerStart = hand.find("seat #") + 6
            dealerEnd = dealerStart + hand[dealerStart:].find("\n")
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            j = 1
            while lines[j][:5]=="Seat ":
                if lines[j].find("sitting out")==-1:
                    numPlayers += 1
                j += 1
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
            winnings = {}
            
            # go through lines to populate seats
            n = 1
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                assert not '$' in player and not ')' in player, "bad player name"
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("(")+2):line.find(")")])
                assert startStacks[player]!=0, "start stack of 0"
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                winnings[player] = 0.
                roundInvestments[player] = 0
                roundActionNum = 1
                n += 1
                if line.find('sitting out')==-1:
                    npl += 1
                      
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to...
            # collect hole card info, check for bad names, find winner
            for line in lines:
                maybePlayerName = line[:line.find(" ")]
                if len(maybePlayerName)==22 and not line.find("sits down")>=0:
                    assert maybePlayerName in seats.keys(), hand
                if maybePlayerName in seats.keys() and line.find("shows [")>=0:
                    hc = line[(line.find("[")+1):line.find("]")]
                    hc = hc.split()
                    holeCards[maybePlayerName] = hc
                elif 'wins' in line:
                    amt = line[(line.find('$')+1):]
                    amt = float(amt[:amt.find(')')])
                    winnings[maybePlayerName] += amt
                
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
                        rd = rd.title().strip()
                        if rd!="Hole Cards":
                            assert roundActionNum!=1, "round with one action"
                            roundActionNum = 1
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
                            assert a!='bet', "illegal action"
                        else:
                            assert a!='call', "illegal action"
                        newRow = {'GameNum':stage,
                                  'RoundActionNum':roundActionNum,
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
                                  'TableName': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt,
                                  'Winnings': winnings[maybePlayerName]
                                  }
                        try:
                            for ii in [1,2]:
                                c = holeCards[maybePlayerName][ii-1]
                                if c is None:
                                    newRow['HoleCard'+str(ii)] = -1
                                else:
                                    newRow['HoleCard'+str(ii)] = deckT.index(c)
                            for ii in range(1,lenBoard+1):
                                newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                            for ii in range(lenBoard+1,6):
                                newRow["Board"+str(ii)] = -1
                        except ValueError:
                            pass
                        data.append(newRow)
                        roundActionNum += 1
            if data[-1]['RoundActionNum']==1:
                data.pop()
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            pass            
        
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
            assert len(table)<=22
            # add dealer
            dealerStart = hand.find("Button:") + 13
            dealerEnd = dealerStart + hand[dealerStart:].find("\n")
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            j = 5
            while lines[j][:5]=="Seat ":
                if lines[j].find("sitting out")==-1:
                    numPlayers += 1
                j += 1
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
            lastNewRoundLine = -1
            winnings = {}
            
            # go through lines to populate seats
            n = 5
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                assert not '$' in player and not ')' in player, "bad player name"
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("(")+2):line.find(")")])
                assert startStacks[player]!=0, "start stack of 0"
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                winnings[player] = 0.
                roundInvestments[player] = 0
                roundActionNum = 1
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to...
            # collect hole card info, check for bad names, find winner
            for line in lines:
                maybePlayerName = line[(line.find(":")+2):(line.find("(")-1)]
                if maybePlayerName in seats.keys() and line.find(", [")>=0:
                    hc = line[(line.find("[")+1):-1]
                    hc = hc.split(", ")
                    holeCards[maybePlayerName] = hc
                elif 'won by' in line:
                    amt = line[(line.find('($')+2):]
                    amt = float(amt[:amt.find(')')])
                    player = line[(line.find('won by')+7):]
                    player = player[:player.find(" ")]
                    winnings[player] += amt

            cardLines = [l for l in lines if l.find(", [")>=0]
            for line in cardLines:
                maybePlayerName = line[(line.find(":")+2):(line.find("(")-1)]
                if line.find("[")>=0:
                    hc = line[(line.find("[")+1):-1]
                    hc = hc.split(", ")
                    holeCards[maybePlayerName] = hc
                
            for line in lines:
                maybePlayerName = line[(line.find(":")+2):(line.find("(")-1)]
                if len(maybePlayerName)==22:
                    assert maybePlayerName in seats.keys()
            
            for j,line in enumerate(lines):
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
                        nar = j - lastNewRoundLine
                        lastNewRoundLine = j
                        for key in roundInvestments:
                            roundInvestments[key] = 0
                        rdStart = line.find("Dealing")+8
                        rdEnd = rdStart + line[rdStart:].find("[") - 1
                        rd = line[rdStart:rdEnd].title().strip()
                        if rd!='Pocket Cards':
                            if nar>1:
                                assert roundActionNum!=1, "round with one action"
                            roundActionNum = 1
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
                            assert a!='bet', "illegal action"
                        else:
                            assert a!='call', "illegal action"
                        newRow = {'GameNum':stage,
                                  'RoundActionNum':roundActionNum,
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
                                  'TableName': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt,
                                  'Winnings': winnings[maybePlayerName]
                                  }
                        try:
                            for ii in [1,2]:
                                c = holeCards[maybePlayerName][ii-1]
                                if c is None:
                                    newRow['HoleCard'+str(ii)] = -1
                                else:
                                    newRow['HoleCard'+str(ii)] = deckT.index(c)
                            for ii in range(1,lenBoard+1):
                                newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                            for ii in range(lenBoard+1,6):
                                newRow["Board"+str(ii)] = -1
                        except ValueError:
                            pass
                        data.append(newRow)
                        roundActionNum += 1
            if data[-1]['RoundActionNum']==1:
                data.pop()
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError) as e:
            pass
        
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
            assert not 'Hand cancelled' in hand, "cancelled hand"
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
            assert len(table)<=22
            # add dealer
            dealerEnd = hand.find("is the button") - 1
            dealerStart = tableEnd + hand[tableEnd:].find("#") + 1
            dealer = int(hand[dealerStart:dealerEnd])
            # add numPlayers
            lines = [s.rstrip() for s in hand.split('\n')]
            numPlayers = 0
            j = 2
            while lines[j][:5]=="Seat ":
                numPlayers += 1
                j += 1
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
            lastNewRoundLine = -1
            sitting = []
            winnings = {}
            
            # go through lines to populate seats
            n = 2
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat" and lines[n].find("button")==-1:
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find('(') - 1
                player = line[playerStart:playerEnd]
                assert not '$' in player and not ')' in player, "bad player name"
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("$")+1):line.find(" in chips")])
                assert startStacks[player]!=0, "start stack of 0"
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                roundInvestments[player] = 0
                winnings[player] = 0.
                roundActionNum = 1
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to...
            # collect hole card info, check for bad names, find winner
            for line in lines:
                maybePlayerName = line[:line.find(":")]
                if line.find('sit')>=0:
                    sitting.append(maybePlayerName)
                if len(maybePlayerName)==22 and maybePlayerName[:5]!="Total":
                    assert maybePlayerName in seats.keys() + sitting or \
                            maybePlayerName.find("***")>=0, maybePlayerName
                if maybePlayerName in seats.keys() and line.find("shows")>=0:
                    hc = line[(line.find("[")+1):line.find("]")]
                    hc = hc.split()
                    holeCards[maybePlayerName] = hc
                elif 'collected' in line and 'from' in line:
                    amt = line[(line.find('$')+1):]
                    amt = float(amt[:amt.find(' ')])
                    player = line[:line.find(" ")]
                    winnings[player] += amt
            
            for j,line in enumerate(lines):
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
                        nar = j - lastNewRoundLine
                        lastNewRoundLine = j
                        for key in roundInvestments:
                            roundInvestments[key] = 0
                        rdStart = line.find(" ")+1
                        rdEnd = rdStart + line[rdStart:].find("*") - 1
                        rd = line[rdStart:rdEnd].title().strip()
                        if rd!='Hole Cards':
                            if nar>1:
                                assert roundActionNum!=1, "round with one action"
                            roundActionNum = 1
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
                            assert a!='bet', "illegal action"
                        else:
                            assert a!='call', "illegal action"
                        newRow = {'GameNum':stage,
                                  'RoundActionNum':roundActionNum,
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
                                  'TableName': table.title(),
                                  'Dealer': dealer,
                                  'NumPlayers': numPlayers,
                                  'LenBoard': lenBoard,
                                  'InvestedThisRound': roundInvestments[maybePlayerName] - amt,
                                  'Winnings': winnings[maybePlayerName]
                                  }
                        try:
                            for ii in [1,2]:
                                c = holeCards[maybePlayerName][ii-1]
                                if c is None:
                                    newRow['HoleCard'+str(ii)] = -1
                                else:
                                    newRow['HoleCard'+str(ii)] = deckT.index(c)
                            for ii in range(1,lenBoard+1):
                                newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                            for ii in range(lenBoard+1,6):
                                newRow["Board"+str(ii)] = -1
                        except ValueError:
                            pass
                        data.append(newRow)
                        roundActionNum += 1
            if data[-1]['RoundActionNum']==1:
                data.pop()
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            pass
        
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
            year = hand[(hand.find("Table") - 6):(hand.find("Table") - 1)]
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
            assert len(table)<=22
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
            winnings = {}
            lenBoard = 0
            lastNewRoundLine = -1
            
            # go through lines to populate seats
            n = 7
            seatnum = 1
            seatnums = []
            while lines[n][:4]=="Seat":
                line = lines[n]
                playerStart = line.find(":")+2
                playerEnd = playerStart + line[playerStart:].find(' ')
                player = line[playerStart:playerEnd]
                assert not '$' in player and not ')' in player, "bad player name"
                seats[player] = seatnum
                seatnum += 1
                seatnums.append(int(line[5:line.find(":")]))
                startStacks[player] = toFloat(line[(line.find("$")+1):(line.find("USD")-1)])
                if not hand.find(player+" has left table"):
                    assert startStacks[player]!=0, "start stack of 0"
                stacks[player] = startStacks[player]
                holeCards[player] = [None, None]
                winnings[player] = 0.
                roundInvestments[player] = 0
                roundActionNum = 1
                npl += 1
                n += 1
            
            # make dealer num relative to missing seats
            dealer = bisect_left(seatnums, dealer) % len(seatnums)

            # go through again to...
            # collect hole card info, check for bad names, find winner
            for line in lines:
                maybePlayerName = line[:line.find(" ")]
                assert line!="** Dealing **"
                if len(maybePlayerName)==22 and not line.find('has joined')>=0:
                    assert maybePlayerName in seats.keys()
                if maybePlayerName in seats.keys() and line.find("shows")>=0:
                    hc = line[(line.find("[")+2):(line.find("]")-1)]
                    hc = hc.split(", ")
                    holeCards[maybePlayerName] = hc
                elif 'wins' in line:
                    amt = line[(line.find('$')+1):]
                    amt = float(amt[:amt.find('USD')])
                    winnings[maybePlayerName] += amt
            
            for j,line in enumerate(lines):
                # skip SUMMARY section by changing lineToRead when encounter it
                # stop skipping once encounter "Game"
                newRow = {}
                maybePlayerName = line[:line.find(" ")]
                
                if line[:6]=="Game #":
                    stage = src + "-" + line[(line.find("#")+1):line.find(" starts")]
                    
                elif line[:2]=="**" and line[:5]!="*****":
                    nar = j - lastNewRoundLine
                    lastNewRoundLine = j
                    for key in roundInvestments:
                        roundInvestments[key] = 0
                    rdStart = line.find(" ")+9
                    rdEnd = rdStart + line[rdStart:].find("*") - 1
                    rd = line[rdStart:rdEnd].title().strip()
                    if rd!='Down Cards':
                        if nar>1:
                            assert roundActionNum!=1, "round with one action"
                        roundActionNum = 1
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
                        assert a!='bet', "illegal action"
                    else:
                        assert a!='call', "illegal action"
                    newRow = {'GameNum':stage,
                              'RoundActionNum':roundActionNum,
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
                              'TableName': table.title(),
                              'Dealer': dealer,
                              'NumPlayers': numPlayers,
                              'LenBoard': lenBoard,
                              'InvestedThisRound': roundInvestments[maybePlayerName] - amt,
                              'Winnings': winnings[maybePlayerName]
                             }
                    try:
                        for ii in [1,2]:
                            c = holeCards[maybePlayerName][ii-1]
                            if c is None:
                                newRow['HoleCard'+str(ii)] = -1
                            else:
                                newRow['HoleCard'+str(ii)] = deckT.index(c)
                        for ii in range(1,lenBoard+1):
                            newRow["Board"+str(ii)] = deckT.index(board[ii-1])
                        for ii in range(lenBoard+1,6):
                            newRow["Board"+str(ii)] = -1
                    except ValueError:
                        pass
                    data.append(newRow)
                    roundActionNum += 1
            if data[-1]['RoundActionNum']==1:
                data.pop()
        except (ValueError, IndexError, KeyError, TypeError, AttributeError, ZeroDivisionError, AssertionError):
            pass
        
    return data

######################## READ ONE FILE ########################################
keys = ['GameNum','RoundActionNum','Date','Time','SeatNum','Round','Player','StartStack',
        'CurrentStack','Action','Amount','AllIn','CurrentBet','CurrentPot','InvestedThisRound',
        'NumPlayersLeft','SmallBlind','BigBlind','TableName','Dealer','NumPlayers','Winnings',
        'LenBoard','HoleCard1','HoleCard2','Board1','Board2','Board3','Board4','Board5']
    
def readFileToDict(filename):
    # get dataframe from one of the source-specific functions
    bf = filename[::-1]
    src = bf[(bf.find('HLN')+3):bf.find('/')][::-1].strip()
    
    # skip ipn, don't have a parser for it
    if src=='ipn':
        return []
        
    # execute read file
    func = 'read{}file'.format(src.upper())
    full = eval('{}("{}")'.format(func, filename))
    
    # list to dict
    d = {}
    for k in keys:
        d[k] = [row[k] if k in row.keys() else '' for row in full]
        
    return d
        
####################### READ ALL FILES ########################################
folders = ["rawdata/"+fdr for fdr in os.listdir('rawdata')]
allFiles = [folder+"/"+f for folder in folders for f in os.listdir(folder)
            if f.find('ipn ')==-1]

# create directories "tables" and "columns" for separate data
for f in ['tables','columns']:
    if not os.path.exists('data/'+f):
        os.mkdir('data/'+f)

# multi-threaded
def worker(tup):
    i,f = tup
    
    # read in data to dictionary
    df = readFileToDict(f)
    
    # write columns to text files
    for col in df:
        writeTo = "data/columns/{}.txt".format(col)
        with open(writeTo, 'ab') as outputFile:
            outputFile.write('\n'.join([str(c) for c in df[col]]) + "\n")
                    
def getData(nFiles):
    startTime = datetime.datetime.now()
        
    # multi-threaded CSV and txt writing
    p = multiprocessing.Pool(8)
    p.map_async(worker,enumerate(allFiles[:nFiles]))
    p.close()
    p.join()
    
    print "Current runtime:", datetime.datetime.now() - startTime

#getData(len(allFiles))
getData(100)


####################### DATA FORMATTING 2: THE SQL ############################
# txt to CSVs, one per table in database
gameFields = ['GameNum','Date','Time','SmallBlind','BigBlind','TableName',
              'Dealer','NumPlayers']
actionFields = ['GameNum','Player','Action','SeatNum','Round','RoundActionNum',
                'StartStack','CurrentStack','Amount','CurrentBet','CurrentPot',
                'InvestedThisRound','NumPlayersLeft','Winnings','HoleCard1','HoleCard2']
boardFields = ['GameNum','Round'] + ['Board'+str(i) for i in range(1,6)]

tableCols = {'games': gameFields, 'actions': actionFields, 'boards': boardFields}

os.chdir('data/columns')
    
for k,v in tableCols.iteritems():
    with open('../tables/{}.csv'.format(k),'w') as fOut:
        fOut.write(','.join(v) + '\n')
    files = ' '.join(fName+'.txt' for fName in v)
    os.system('paste -d"," {} >> ../tables/{}.csv'.format(files,k))

# import CSVs to database tables
os.chdir('../tables')

# remove duplicate rows from board, game CSVs
os.system('sort -u boards.csv -o boards.csv')
os.system('sort -u games.csv -o games.csv')

# write headers to files
for k,v in tableCols.iteritems():
    with open('{}2.csv'.format(k),'w') as f:
        f.write(','.join(v) + '\n')
    os.system('cat {0}.csv >> {0}2.csv'.format(k))
    os.remove('{}.csv'.format(k))
    os.rename('{}2.csv'.format(k),'{}.csv'.format(k))

# get password from file
with open('../../pwd.txt') as f:
    pwd = f.read().strip()

# connect to DB
db = MySQLdb.connect(host='localhost',port=3307,user='ntaylorwss',passwd=pwd,
                     db='poker')
cursor = db.cursor()

# queries to create tables
createBoardsQuery = """create table boards
                    ( GameNum varchar(22),
                      Round varchar(7),
                      Board1 tinyint(2),
                      Board2 tinyint(2),
                      Board3 tinyint(2),
                      Board4 tinyint(2),
                      Board5 tinyint(2),
                      BoardID int NOT NULL,
                      PRIMARY KEY (BoardID)
                    );"""

createActionsQuery = """create table actions 
                    ( GameNum varchar(22),
                      Player varchar(22),
                      Action varchar(10),
                      SeatNum tinyint(2),
                      Round varchar(7),
                      RoundActionNum tinyint(2),
                      Amount decimal(8,2),
                      StartStack decimal(8,2),
                      CurrentStack decimal(8,2),
                      CurrentBet decimal(8,2),
                      CurrentPot decimal(8,2),
                      InvestedThisRound decimal(8,2),
                      NumPlayersLeft tinyint(2),
                      Winnings decimal(8,2),
                      HoleCard1 tinyint(2),
                      HoleCard2 tinyint(2),
                      ActionID int NOT NULL,
                      PRIMARY KEY (ActionID),
                      FOREIGN KEY (GameNum) REFERENCES games (GameNum)
                    );"""
                    
createGamesQuery = """create table games 
                    ( GameNum varchar(22),
                      Date date,
                      Time time,
                      SmallBlind decimal(2,2),
                      BigBlind decimal(2,2),
                      TableName varchar(22),
                      Dealer tinyint(2),
                      NumPlayers tinyint(2),
                      PRIMARY KEY (GameNum)
                    );"""

for q in [createGamesQuery,createBoardsQuery,createActionsQuery]: cursor.execute(q)

# query to add CSV data to tables
importQuery = """LOAD DATA LOCAL INFILE '{}'
                INTO TABLE {}
                FIELDS TERMINATED BY ','
                OPTIONALLY ENCLOSED BY '"'
                LINES TERMINATED BY '\\n'
                IGNORE 1 LINES
                ({});"""

# games, then boards, then actions
'''
for f in sorted(os.listdir(os.getcwd()))[::-1]:
    table = f[:-4]
    try:
        cursor.execute(importQuery.format(f, table, ','.join(tableCols[table])))
        db.commit()
    except Exception:
        db.rollback()
'''