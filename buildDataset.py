'''
import os
import gc
import pandas as pd
import numpy as np
from datetime import datetime
from bisect import bisect_left
import csv
from itertools import izip, product, combinations

############################ CREATE TEST FILES ################################
# write sample txt files
for filename in os.listdir('data/columns'):
    with open('data/columns/{}'.format(filename)) as fIn, \
            open('testdata/{}'.format(filename),'w') as fOut:
        col = []
        for i,d in enumerate(fIn):
            if i >= 10000:
                break
            col.append(d)
        fOut.write(''.join(col))

############################### TABLE FEATURES ################################
# CREATE FEATURE SET
tableFiles = ['data/tables/{}'.format(f) for f in os.listdir('data/tables')]
columnFiles = ["data/columns/"+f for f in os.listdir('data/columns')]
testTableFiles = tableFiles[:1]
testColumnFiles = ['testdata/{}'.format(f) for f in os.listdir('testdata')]

actions = ['none','deadblind','blind','fold','check','call','bet','raise']

def basicAction(a):
    if a[:3]=='bet':
        return 'bet'
    elif a[:5]=='raise':
        return 'raise'
    else:
        return a
'''

'''
startTime = datetime.now()
for ii,filename in enumerate(testTableFiles):
    #### PREP ####
    
    # read in data
    poker = pd.read_csv(filename)
    print "READ IN POKER:", datetime.now() - startTime
    
    # helper columns
    poker['SeatRelDealer'] = np.where(poker.SeatNum > poker.Dealer,
                                        poker.SeatNum - poker.Dealer,
                                        poker.Dealer - poker.SeatNum)
    poker['BasicAction'] = poker.Action.apply(basicAction)
    poker = poker.join(pd.get_dummies(poker.Action).astype(int))
    
    # start feature set
    pokerWOB = pd.DataFrame(poker.ix[~((poker.Action=='blind') | (poker.Action=='deadblind'))])
    featureSet = pd.DataFrame({'Player': pokerWOB.Player, 'Action': pokerWOB.Action}, index=pokerWOB.index)
    
    # discretize actions
    pokerWOB['BetOverPot'] =  pokerWOB.Amount / pokerWOB.CurrentPot
    bins = [0., 0.25, 0.5, 0.75, 1., 2.]
    featureSet['Action'] = [a + str(bins[bisect_left(bins, b)-1])
                            if a=='bet' or a=='raise' else a
                            for a,b in zip(pokerWOB.Action, pokerWOB.BetOverPot)]
    
    #Round and FB (splitting features)
    featureSet['Round'] = pokerWOB.Round
    featureSet['FacingBet'] = (pokerWOB.CurrentBet > pokerWOB.InvestedThisRound).astype(int)

    #### GAME STATE FEATURES ####

    # amount to call
    featureSet['AmountToCall'] = pokerWOB.CurrentBet - pokerWOB.InvestedThisRound

    # current pot
    featureSet['CurrentPot'] = pokerWOB.CurrentPot

    # number of players at start of game
    featureSet['NumPlayersStart'] = pokerWOB.NumPlayers

    # number of players remaining
    featureSet['NumPlayersLeft'] = pokerWOB.NumPlayersLeft

    # big blind
    featureSet['BigBlind'] = pokerWOB.BigBlind

    # number of checks so far in the game
    featureSet['NumChecksGame'] = pokerWOB.groupby('GameNum').check.cumsum()

    # last to act
    relevantCols = ['GameNum','Round','SeatRelDealer','Action']
    ltaDF = zip(*[poker[c] for c in relevantCols])
    LTAbyRow = []
    m = len(ltaDF)
    for i,(gameNum,rd,seat,action) in enumerate(ltaDF):
        ap = []
        windowStart = i
        windowEnd = i
        while windowStart>=0 and ltaDF[windowStart][:2]==(gameNum,rd):
            if ltaDF[windowStart][3]!='fold':
                ap.append(ltaDF[windowStart][2])
            windowStart -= 1
        while windowEnd<m and ltaDF[windowEnd][:2]==(gameNum,rd):
            ap.append(ltaDF[windowEnd][2])
            windowEnd += 1
        LTAbyRow.append(min(ap))
    featureSet['LastToAct'] = [LTAbyRow[i] for i in pokerWOB.index]
    del LTAbyRow
    gc.collect()

    # last to act stack
    ltasDF = zip(pokerWOB.GameNum, pokerWOB.CurrentStack, pokerWOB.SeatRelDealer, featureSet.LastToAct)
    LTASbyRow = []
    m = len(ltasDF)
    for i,(gameNum,stack,seat,lta) in enumerate(ltasDF):
        s = 0
        windowStart = i
        windowEnd = i
        while windowStart>=0 and ltasDF[windowStart][0]==gameNum:
            r = ltasDF[windowStart]
            if r[3]==r[2]:
                s = r[1]
                break
            windowStart -= 1
        if s==0:
            while windowEnd<m and ltasDF[windowEnd][0]==gameNum:
                r = ltasDF[windowEnd]
                if r[3]==r[2]:
                    s = r[1]
                    break
                windowEnd += 1
        LTASbyRow.append(s)
    featureSet['LastToActStack'] = LTASbyRow
    del LTASbyRow
    gc.collect()

    # final pot of last hand at table
    relevantCols = ['GameNum','Table','CurrentPot']
    tlhpDF = zip(*[pokerWOB[c] for c in relevantCols])
    TLHPbyRow = []
    tableLastHandPot = {}
    for i,(gameNum,table,cp) in enumerate(tlhpDF):
        if not table in tableLastHandPot:
            tableLastHandPot[table] = -1
        TLHPbyRow.append(tableLastHandPot[table])
        if (i+1)<len(tlhpDF) and gameNum!=tlhpDF[i+1][0]:
            tableLastHandPot[table] = cp
    featureSet['FinalPotLastHandTable'] = TLHPbyRow
    del TLHPbyRow
    gc.collect()

    # current bet is the raise part of a check-raise move
    pokerWOB['PrevAction'] = poker.groupby(['GameNum','Player']).Action.shift(1).ix[pokerWOB.index].fillna('none')
    featureSet['CBisCheckRaise'] = (pokerWOB.PrevAction=='check') & (featureSet.Action=='raise')

    # cumulative total of bets and raises for game
    pokerWOB['BetOrRaise'] = pokerWOB.bet | pokerWOB['raise']
    featureSet['BetsRaisesGame'] = pokerWOB.groupby('GameNum').BetOrRaise.cumsum()

    # total bets and raises for each round
    relevantCols = ['GameNum','Round','BetOrRaise']
    brDF = zip(*[pokerWOB[c] for c in relevantCols])
    PFcol,Fcol,Tcol,Rcol = [[],[],[],[]]
    countPF,countF,countT,countR = [0,0,0,0]
    for i,(g,r,bor) in enumerate(brDF):
        if g!=brDF[i-1][0]:
            countPF,countF,countT,countR = [0,0,0,0]
        PFcol.append(countPF)
        Fcol.append(countF)
        Tcol.append(countT)
        Rcol.append(countR)
        if r=='Preflop': countPF += bor
        if r=='Flop': countF += bor
        if r=='Turn': countT += bor
        if r=='River': countR += bor
    featureSet['BetsRaisesPF'] = PFcol
    featureSet['BetsRaisesF'] = Fcol
    featureSet['BetsRaisesT'] = Tcol
    featureSet['BetsRaisesR'] = Rcol

    #### BOARD FEATURES #########
    # break DF into suits (vals in range(4)) and ranks (vals in range(13))
    boardDF = pokerWOB[['Board'+str(i) for i in range(1,6)]]
    boardSuits = boardDF%4
    boardRanks = boardDF%13
    
    # build DFs of rank counts and suit counts (nrow*13 and nrow*4 dims)
    rankCountsFlop, rankCountsTurn, rankCountsRiver = [{},{},{}]
    for r in xrange(13):
        rankCountsFlop[r] = list((boardRanks.ix[:,:2]==r).sum(axis=1))
        rankCountsTurn[r] = list((boardRanks.ix[:,:3]==r).sum(axis=1))
        rankCountsRiver[r] = list((boardRanks==r).sum(axis=1))
    rankCountsFlop = pd.DataFrame(rankCountsFlop)
    rankCountsTurn = pd.DataFrame(rankCountsTurn)
    rankCountsRiver = pd.DataFrame(rankCountsRiver)
    
    suitCountsFlop, suitCountsTurn, suitCountsRiver = [{},{},{}]
    for r in xrange(13):
        suitCountsFlop[r] = list((boardSuits.ix[:,:2]==r).sum(axis=1))
        suitCountsTurn[r] = list((boardSuits.ix[:,:3]==r).sum(axis=1))
        suitCountsRiver[r] = list((boardSuits==r).sum(axis=1))
    suitCountsFlop = pd.DataFrame(suitCountsFlop)
    suitCountsTurn = pd.DataFrame(suitCountsTurn)
    suitCountsRiver = pd.DataFrame(suitCountsRiver)
    
    # Number of pairs on the board
    featureSet['NumPairsFlop'] = (rankCountsFlop==2).sum(axis=1)
    featureSet['NumPairsTurn'] = (rankCountsTurn==2).sum(axis=1)
    featureSet['NumPairsRiver'] = (rankCountsRiver==2).sum(axis=1)
    
    # Flush draw on the flop (2 to a suit, not 3)
    featureSet['TwoToFlushDrawFlop'] = (suitCountsFlop==2).sum(axis=1)>0
    
    # Flush draw on the flop (3 to a suit)
    featureSet['ThreeToFlushDrawFlop'] = (suitCountsFlop==3).sum(axis=1)>0
    
    # Flush draw on the turn (still 2 to a suit, not 3)
    featureSet['TwoToFlushDrawTurn'] = (suitCountsTurn==2).sum(axis=1)>0
    
    # Flush draw connects on the turn (from 2 to 3)
    featureSet['FlushTurned'] = (featureSet.TwoToFlushDrawFlop) & \
                            ((suitCountsTurn==3).sum(axis=1)>0)
                            
    # Flush draw connects on the river (from 2 to 3)
    featureSet['FlushRivered'] = (featureSet.TwoToFlushDrawTurn) & \
                            ((suitCountsRiver==3).sum(axis=1)>0)
    
    # High card on each street
    featureSet['HighCardFlop'] = boardRanks.ix[:,:2].max(axis=1)
    featureSet['HighCardTurn'] = boardRanks.ix[:,:3].max(axis=1)
    featureSet['HighCardRiver'] = boardRanks.max(axis=1)
    
    # Range of cards on each street
    featureSet['RangeFlop'] = featureSet.HighCardFlop - boardRanks.ix[:,:2].min(axis=1)
    featureSet['RangeTurn'] = featureSet.HighCardTurn - boardRanks.ix[:,:3].min(axis=1)
    featureSet['RangeRiver'] = featureSet.HighCardRiver - boardRanks.min(axis=1)
    
    # build DF of card ranks differences (1-2, 1-3, ..., 4-5) for straight draw finding
    diffs = {}
    for a,b in product(range(5), range(5)):
        if a!=b:
            k = '-'.join([str(a+1),str(b+1)])
            if not k in diffs:
                diffs[k] = []
            diffs[k].append(list(abs(boardRanks.ix[:,a] - boardRanks.ix[:,b]))[0])
    diffs = pd.DataFrame(diffs)
    
    # 2 to a straight draw on each flop, turn
    diffsFlop = diffs[[c for c in diffs.columns
                        if not ('3' in c or '4' in c)]]
    featureSet['TwoToStraightDrawFlop'] = ((diffsFlop==1).sum(axis=1))>=1 
    
    diffsTurn = diffs[[c for c in diffs.columns if not '4' in c]]
    featureSet['TwoToStraightDrawTurn'] = ((diffsTurn==1).sum(axis=1))>=1
    
    # 3+ to a straight on flop
    featureSet['ThreeToStraightFlop'] = featureSet.RangeFlop==2
    
    # 3+ to a straight on turn
    comboRanges = []
    for cards in combinations(range(4),3):
        c = boardRanks.ix[:,cards]
        comboRanges.append((c.max(axis=1) - c.min(axis=1) == 2) & (c.notnull().sum(axis=1)==3))
    featureSet['ThreeOrMoreToStraightTurn'] = pd.DataFrame(comboRanges).sum()>0
    
    # 3+ to a straight on river
    comboRanges = []
    for cards in combinations(range(5),3):
        c = boardRanks.ix[:,cards]
        comboRanges.append((c.max(axis=1) - c.min(axis=1) == 2) & (c.notnull().sum(axis=1)==3))
    featureSet['ThreeOrMoreToStraightRiver'] = pd.DataFrame(comboRanges).sum()>0
    
    # turn is over card (greater than max(flop))
    featureSet['TurnOverCard'] = boardRanks['Board4'] > boardRanks.ix[:,:3].max(axis=1)
    
    # river is over card (greater than max(flop+turn))
    featureSet['RiverOverCard'] = boardRanks['Board5'] > boardRanks.ix[:,:4].max(axis=1)
    
    # num face cards each street
    featureSet['NumFaceCardsFlop'] = (boardRanks.ix[:,:3]>=9).sum(axis=1)
    featureSet['NumFaceCardsTurn'] = (boardRanks.ix[:,:4]>=9).sum(axis=1)
    featureSet['NumFaceCardsRiver'] = (boardRanks>=9).sum(axis=1)
    
    # average card rank
    featureSet['AvgCardRankFlop'] = (boardRanks.ix[:,:3]).mean(axis=1)
    featureSet['AvgCardRankTurn'] = (boardRanks.ix[:,:4]).mean(axis=1)
    featureSet['AvgCardRankRiver'] = boardRanks.mean(axis=1)
    
    # turn is a brick (5 or less and not pair and not making a flush)
    featureSet['TurnBrick'] = (boardRanks.Board4<=5) & (featureSet.NumPairsFlop==featureSet.NumPairsTurn) & (~featureSet.FlushTurned)
    
    # river is a brick (5 or less and not pair and not making a flush)
    featureSet['RiverBrick'] = (boardRanks.Board5<=5) & (featureSet.NumPairsTurn==featureSet.NumPairsRiver) & (~featureSet.FlushRivered)
    
    #### OPPONENT FEATURES ######
    # mean/SD/max/min other stack, relative to big blind, relative to self
    relevantCols = ['GameNum','Round','Player','Action','CurrentStack','BigBlind']
    osDF = zip(*[poker[c] for c in relevantCols])
    meanByRow,sdByRow,maxByRow,minByRow = [[],[],[],[]]
    m = len(osDF)
    for i,(gameNum,rd,player,action,currentStack,bb) in enumerate(osDF):
        otherStacks = []
        windowStart = i
        windowEnd = i
        while windowStart>=0 and osDF[windowStart][:2]==(gameNum,rd):
            r = osDF[windowStart]
            if r[2]!=player and r[3]!='fold':
                otherStacks.append(r[4])
            windowStart -= 1
        while windowEnd<m and osDF[windowEnd][:2]==(gameNum,rd):
            row = osDF[windowEnd]
            if row[2]!=player:
                otherStacks.append(r[4])
            windowEnd += 1
        stacks = [(s-currentStack)/bb for s in otherStacks]
        meanByRow.append(np.mean(stacks))
        sdByRow.append(np.std(stacks))
        maxByRow.append(np.max(stacks))
        minByRow.append(np.min(stacks))
    featureSet['MeanOtherStackRelBBRelSelf'] = [meanByRow[i] for i in pokerWOB.index]
    featureSet['SDOtherStackRelBBRelSelf'] = [sdByRow[i] for i in pokerWOB.index]
    featureSet['MaxOtherStackRelBBRelSelf'] = [maxByRow[i] for i in pokerWOB.index]
    featureSet['MinOtherStackRelBBRelSelf'] = [minByRow[i] for i in pokerWOB.index]
    del meanByRow,sdByRow,maxByRow,minByRow
    gc.collect()
    
    # aggressor position, aggressor stack, aggressor in position vs me
    agg = (poker.bet | poker['raise']).astype(bool)
    featureSet['AggressorPos'] = (poker.SeatRelDealer*agg).replace(to_replace=0, method='ffill').ix[pokerWOB.index]
    featureSet['AggInPosVsMe'] = featureSet.AggressorPos < pokerWOB.SeatRelDealer
    featureSet['AggStack'] = (poker.CurrentStack*agg).replace(to_replace=0,method='ffill').ix[pokerWOB.index]
    
    #### PLAYER FEATURES ########
    # is player the aggressor
    featureSet['IsAgg'] = agg.ix[pokerWOB.index]
    
    # position relative to dealer, relative to number of players
    featureSet['SeatRelDealerRelNP'] = pokerWOB.SeatRelDealer / pokerWOB.NumPlayers

    # effective stack
    relevantCols = ['GameNum','Round','Player','Action','CurrentStack']
    esDF = zip(*[poker[c] for c in relevantCols])
    ESbyRow = []
    m = len(esDF)
    for i,(gameNum,rd,player,action,currentStack) in enumerate(esDF):
        es = []
        windowStart = i
        windowEnd = i
        maxOtherStack = 0
        while windowStart>=0 and esDF[windowStart][:2]==(gameNum,rd):
            r = esDF[windowStart]
            if r[2]!=player and r[4]>maxOtherStack and r[3]!='fold':
                maxOtherStack = r[4]
            windowStart -= 1
        while windowEnd<m and esDF[windowEnd][:2]==(gameNum,rd):
            row = esDF[windowEnd]
            if row[2]!=player and r[4]>maxOtherStack:
                maxOtherStack = r[4]
            windowEnd += 1
        ESbyRow.append(es)
    featureSet['EffectiveStack'] = [ESbyRow[i] for i in pokerWOB.index]
    del ESbyRow
    gc.collect()
    
    # effective stack vs aggressor
    featureSet['ESvsAgg'] = (featureSet.AggStack>=pokerWOB.CurrentStack)*featureSet.AggStack + \
                            (pokerWOB.CurrentStack>=featureSet.AggStack)*pokerWOB.CurrentStack
                            
    # stack to pot ratio
    featureSet['StackToPot'] = pokerWOB.CurrentStack / pokerWOB.CurrentPot
    
    # am I small blind
    featureSet['IsSB'] = pokerWOB.SeatRelDealer==1

    # am I big blind
    featureSet['IsBB'] = pokerWOB.SeatRelDealer==2
    
    # how much have I committed so far this game
    featureSet['InvestedThisGame'] = pokerWOB.StartStack - pokerWOB.CurrentStack
    
    # WRITE TABLE TO COLUMN FILES
    print "FEATURE SET COMPLETE", datetime.now() - startTime
    if ii==0:
        openFiles = [open('{}.txt'.format(c),'ab') for c in featureSet.columns]
    for i,c in enumerate(featureSet.columns):
        openFiles[i].write('\n'.join(str(featureSet[c])) + '\n')
    print "FEATURES WRITTEN TO TXT", datetime.now() - startTime
'''

############################ COLUMN FEATURES ##############################

#os.chdir('data/columns')
os.chdir('testdata')

# player's last action
with open('Player.txt') as playerF, open('Action.txt') as actionF, \
        open('LastAction.txt','ab') as outF:
    pla = []
    lastActions = {}
    for i,(p,a) in enumerate(izip(playerF, actionF)):
        p,a = (p.strip(), a.strip())
        if p in lastActions:
            pla.append(lastActions[p])
        else:
            pla.append('None')
        lastActions[p] = a
        if i % 10000000 == 0:
            outF.write('\n'.join(pla))
            pla = []
    outF.write('\n'.join(pla))
    pla = None

# players' actions by round as percentages
with open('Player.txt') as playerF, open('Action.txt') as actionF, \
        open('Round.txt') as roundF:
    rounds = ['Preflop','Flop','Turn','River','All']
    actions = ['fold','check','call','bet','raise']
    playersActionsByRound = {}
    colsToBeWritten = {a: {r:[] for r in rounds} for a in actions}
    for p,a,r in izip(playerF, actionF, roundF):
        p,a,r = (p.strip(), a.strip(), r.strip())
        if a in ['blind','deadblind'] or p=='': continue
        if p in playersActionsByRound:
            if a in playersActionsByRound[p]:
                if r in playersActionsByRound[p][a]:
                    playersActionsByRound[p][a][r] += 1.
                else:
                    playersActionsByRound[p][a][r] = 1.
                playersActionsByRound[p][a]['All'] += 1.
            else:
                playersActionsByRound[p][a] = {r:1., 'All':1.}
        else:
            playersActionsByRound[p] = {a:{r:1., 'All':1.}}
with open('Player.txt') as playerF, open('Action.txt') as actionF:
    for i,(p,a) in enumerate(izip(playerF,actionF)):
        p,a = (p.strip(), a.strip())
        if a in ['blind','deadblind']: continue
        actionsByRound = playersActionsByRound[p]
        # fill all missing keys, e.g. player never folded on flop add a 0 there
        for a in actions:
            if not a in actionsByRound:
                actionsByRound[a] = {r:0. for r in rounds}
            else:
                for r in rounds:
                    if not r in actionsByRound[a]:
                        actionsByRound[a][r] = 0.
        # collect
        for a in actions:
            byRound = actionsByRound[a]
            for r in rounds[:-1]:
                numAinR = sum(actionsByRound[A][r] for A in actions)
                if numAinR!=0:
                    rAsPct = byRound[r] / numAinR
                else:
                    rAsPct = 0.
                colsToBeWritten[a][r].append(rAsPct)
            colsToBeWritten[a]['All'].append(byRound['All'])
        if i % 10000000 == 0:
            for a in actions:
                for r in rounds:
                    f = open('{}{}Pct.txt'.format(r,a[:1].upper()+a[1:]),'ab')
                    f.write('\n'.join(colsToBeWritten[a][r]) + '\n')
                    f.close()
            colsToBeWritten[a][r] = []
    for a in actions:
        for r in rounds:
            f = open('{}{}Pct.txt'.format(r,a[:1].upper()+a[1:]),'ab')
            f.write('\n'.join(colsToBeWritten[a][r]))
            f.close()
    colsToBeWritten,playerActionsByRound = [None,None]

# TODO: resume checking from HERE DOWN

# VPIP (voluntarily put $ in pot)
# preflop raise %
with open('Player.txt') as playerF, open('Round.txt') as roundF, \
        open('Action.txt') as actionF:
    vpip = []
    pfr = []
    playersCalls = {}
    playersRaises = {}
    playersPreflopOps = {}
    for p,r,a in izip(playerF, roundF, actionF):
        if r=='Preflop':
            if p in playersPreflopOps:
                playersPreflopOps[p] += 1.
                playersCalls[p] += a=='call'
                playersRaises[p] += a=='raise'
            else:
                playersPreflopOps[p] = 1.
                playersCalls[p] = a=='call'
                playersRaises[p] = a=='raise'
with open('Player.txt') as playerF, open('VPIP.txt','ab') as vpipF, \
        open('PreflopRaisePct','ab') as pfrF:
    for i,p in enumerate(playerF):
        vpip.append(playersCalls[p]+playersRaises[p] / playersPreflopOps[p])
        pfr.append(playersRaises[p] / playersPreflopOps)
        if i % 10000000 == 0:
            vpipF.write('\n'.join(vpip) + '\n')
            pfrF.write('\n'.join(pfr) + '\n')
            vpip = []
            pfr = []
    vpipF.write('\n'.join(vpip))
    pfrF.write('\n'.join(pfr))
    vpip,pfr,playersCalls,playersRaises,playersPreflopOps = [None,None,None,None]
    
# net at table
with open('Player.txt') as playerF, open('Table.txt') as tableF, \
        open('CurrentStack.txt') as csF, open('StartStack.txt') as ssF, \
        open('NetAtTable.txt','ab') as outF:
    nat = []
    playerTableStartStacks = {}
    for p,t,c,s in izip(playerF, tableF, csF, ssF):
        c = float(c)
        s = float(s)
        if p in playerTableStartStacks:
            if t in playerTableStartStacks[p]:
                # player seen at table before, take difference
                nat.append(c - playerTableStartStacks[p][t])
            else:
                # player not seen at table before, record start stack at table, take 0
                playerTableStartStacks[p][t] = s
                nat.append(0)
        else:
            # player not seen before, record first table start stack, take 0
            playerTableStartStacks[p] = {t: s}
            nat.append(0)
        if i % 10000000 == 0:
            outF.write('\n'.join(nat) + '\n')
            nat = []
    outF.write('\n'.join(nat))
    nat,playerTableStartStacks = [None,None]

# sd of VPIP for each player
with open('Player.txt') as playerF, open('VPIP.txt') as vpipF:
    sdv = []
    playerVPIP = {}
    for p,v in izip(playerF, vpipF):
        v = float(v)
        if p in playerVPIP:
            playerVPIP[p].append(v)
        else:
            playerVPIP[p] = [v]
    for p in playerVPIP:
        playerVPIP[p] = np.std(playerVPIP[p])
with open('Player.txt') as playerF, open('sdVPIP.txt','ab') as outF:
    for i,p in enumerate(playerF):
        sdv.append(playerVPIP[p])
        if i % 10000000 == 0:
            outF.write('\n'.join(sdv) + '\n')
            sdv = []
    outF.write('\n'.join(sdv))
    sdv,playerVPIP = [None,None]

# 3-bet %
with open('Player.txt') as playerF, open('Round.txt') as roundF, \
        open('Action.txt') as actionF:
    threeBets = []
    player3Bets = {}
    player3BetOpps = {}
    lastRowRound = ''
    for p,r,a in izip(playerF, roundF, actionF):
        if r!=lastRowRound:
            better = ''
            raiser = ''
        if a=='bet':
            better = p
        if a=='raise':
            raiser = p
        if a!='bet' and better==p:
            if p in player3BetOpps:
                player3Bets += a=='raise'
                player3BetOpps[p] += 1.
            else:
                player3Bets = a=='raise'
                player3BetOpps[p] = 1.
        lastRowRound = r
with open('Player.txt') as playerF, open('ThreeBetPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        threeBets.append(player3Bets[p] / player3BetOpps[p])
        if i % 10000000 == 0:
            outF.write('\n'.join(threeBets) + '\n')
            threeBets = []
    outF.write('\n'.join(threeBets))
    threeBets,player3Bets,player3BetOpps = [None,None,None]
        
# see showdown %
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('HoleCard1.txt') as cardF:
    ssPct = []
    playerGameSeesSD = {}
    for p,g,c in izip(playerF, gameF, cardF):
        if p in playerGameSeesSD:
            if not g in playerGameSeesSD[p]:
                playerGameSeesSD[p][g] = c!='-1'
        else:
            playerGameSeesSD[p] = {g: c!='-1'}
with open('Player.txt') as playerF, open('SeeShowdownPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        allG = playerGameSeesSD[p].values()
        ssPct.append(np.mean(allG))
        if i % 10000000 == 0:
            outF.write('\n'.join(ssPct) + '\n')
            ssPct = []
    outF.write('\n'.join(ssPct))
    ssPct,playerGameSeesSD = [None,None]

# average commitment folded
with open('Player.txt') as playerF, open('Action.txt') as actionF, \
        open('InvestedThisGame.txt') as investF, open('BigBlind.txt') as bbF:
    comfold = []
    playerComFolds = {}
    for p,a,v,b in izip(playerF, actionF, investF, bbF):
        v = float(v)
        b = float(b)
        if a=='fold' and v!=b:
            if p in playerComFolds:
                playerComFolds[p].append(v)
            else:
                playerComFolds[p] = [v]
with open('Player.txt') as playerF, open('AvgCommitFolded') as outF:
    for i,p in enumerate(playerF):
        comfold.append(np.mean(playerComFolds[p]))
        if i % 10000000 == 0:
            outF.write('\n'.join(comfold) + '\n')
            comfold = []
    outF.write('\n'.join(comfold))
    comfold,playerComFolds = [None,None]
            
# aggression factor overall
def getAF(r):
    with open('{}BetPct.txt'.format(r)) as betF, open('{}RaisePct.txt'.format(r)) as raiseF, \
            open('{}CallPct.txt'.format(r)) as callF, open('{}AggFactor.txt'.format(r),'ab') as outF:
        af = []
        for b,r,c in izip(betF, raiseF, callF):
            b = float(b)
            r = float(r)
            c = float(c)
            af.append((b+r)/c)
            if i % 10000000 == 0:
                outF.write('\n'.join(af) + '\n')
                af = []
        outF.write('\n'.join(af))
        af = None
        
getAF('All')

# aggression factor on flop
getAF('Flop')
# aggression factor on turn
getAF('Turn')
# aggression factor on river
getAF('River')

# win % when see flop
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('Round.txt') as roundF, open('Winnings.txt') as winF:
    wf = []
    playerFlopWins = {}
    playerFlopOpps = {}
    for p,g,r,w in izip(playerF, gameF, roundF, winF):
        w = float(w)
        if r!='Preflop':
            if p in playerFlopOpps:
                if not g in playerFlopOpps[p]:
                    playerFlopOpps[p].add(g)
                    playerFlopWins[p] += w>0
            else:
                playerFlopOpps[p] = {g}
                playerFlopWins[p] = w>0
with open('Player.txt') as playerF, open('WinWhenSeeFlopPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        wf.append(float(playerFlopWins[p]) / len(playerFlopOpps[p]))
        if i % 10000000 == 0:
            outF.write('\n'.join(wf) + '\n')
            wf = []
    outF.write('\n'.join(wf))
    wf,playerFlopWins,playerFlopOpps = [None,None,None]

# win without showdown % (wins without showdown / total wins)
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('HoleCard1.txt') as cardF, open('Winnings.txt') as winF:
    wws = []
    playerWinsWSD = {}
    playerWins = {}
    for i,(p,g,c,w) in enumerate(izip(playerF, gameF, cardF, winF)):
        if w:
            if p in playerWins:
                playerWins[p].add(g)
                if c=='-1':
                    playerWinsWSD[p].add(g)
            else:
                playerWins[p] = {g}
                if c=='-1':
                    playerWinsWSD[p] = {g}
with open('Player.txt') as playerF, open('WinWithoutShowdownPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        wws.append(float(len(playerWinsWSD[p])) / len(playerWins[p]))
        if i % 10000000 == 0:
            outF.write('\n'.join(wws) + '\n')
            wws = []
    outF.write('\n'.join(wws))
    wws,playerWinsWSD,playerWins = [None,None,None]

# win % at showdown
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('HoleCard1.txt') as cardF, open('Winnings.txt') as winF:
    ws = []
    playerWinsAtSD = {}
    playerShowdowns = {}
    for i,(p,g,c,w) in enumerate(izip(playerF, gameF, cardF, winF)):
        w = float(w)
        if c!='-1':
            if p in playerWinsAtSD:
                playerShowdowns[p].add(g)
                if w:
                    playerWinsAtSD[p].add(g)
            else:
                playerShowdowns[p] = {g}
                if w:
                    playerWinsAtSD[p] = {g}
with open('Player.txt') as playerF, open('WinAtShowdownPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        ws.append(float(len(playerWinsAtSD[p])) / len(playerShowdowns[p]))
        if i % 10000000 == 0:
            outF.write('\n'.join(ws) + '\n')
            ws = []
    outF.write('\n'.join(ws))
    ws,playerWinsAtSD,playerShowdowns = [None,None,None]

# continuation bet %
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('Round.txt') as roundF, open('Action.txt') as actionF:
    cb = []
    playerContBets = {}
    playerContBetOpps = {}
    lastG = ''
    for i,(p,g,r,a) in enumerate(izip(playerF, gameF, roundF, actionF)):
        if not r in ['Preflop','Flop']:
            continue
        if g!=lastG:
            agg = ''
        if r=='Preflop':
            if a=='raise':
                agg = p
        elif r=='Flop':
            if p==agg:
                if p in playerContBetOpps:
                    playerContBetOpps[p] += 1.
                else:
                    playerContBetOpps[p] = 1.
                    playerContBets[p] = 0.
                playerContBets[p] += a=='bet'
with open('Player.txt') as playerF, open('ContBetPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        if p in playerContBets:
            cb.append(playerContBets[p] / playerContBetOpps[p])
        else:
            cb.append(-1)
        if i % 10000000 == 0:
            outF.write('\n'.join(cb))
            cb = []
    cb,playerContBets,playerContBetOpps = [None,None,None]

# bet river %
with open('Player.txt') as playerF, open('Round.txt') as roundF, \
        open('Action.txt') as actionF:
    br = []
    playerRiverBets = {}
    playerRiverOpps = {} # bets and checks
    for i,(p,r,a) in enumerate(izip(playerF, roundF, actionF)):
        if r=='River':
            if p in playerRiverOpps:
                playerRiverOpps[p] += a in ['bet','check']
                playerRiverBets[p] += a=='bet'
            else:
                playerRiverOpps[p] = a in ['bet','check']
                playerRiverBets[p] = a=='bet'
with open('Player.txt') as playerF, open('BetRiverPct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        br.append(float(playerRiverBets[p]) / playerRiverOpps[p])
        if i % 10000000 == 0:
            outF.write('\n'.join(br) + '\n')
            br = []
    outF.write('\n'.join(br))
    br,playerRiverBets,playerRiverOpps = [None,None,None]
    
# call/raise preflop raise %
with open('Player.txt') as playerF, open('Round.txt') as roundF, \
        open('GameNum.txt') as gameF, open('Action.txt') as actionF:
    cpfr = []
    playerPFRCalls = {}
    playerPFROpps = {}
    lastRaiseG = ''
    for i,(p,r,g,a) in enumerate(izip(playerF, roundF, gameF, actionF)):
        if r!='Preflop':
            continue
        if a=='raise':
            lastRaiseG = g
        if g==lastRaiseG:
            if p in playerPFROpps:
                playerPFROpps[p] += 1
            else:
                playerPFROpps[p] = 1
                playerPFRCalls[p] = 0.
            if a in ['call','raise']:
                playerPFRCalls[p] += 1.
with open('Player.txt') as playerF, open('CallPreflopRaisePct.txt','ab') as outF:
    for i,p in enumerate(playerF):
        cpfr.append(playerPFRCalls[p] / playerPFROpps[p])
        if i % 10000000 == 0:
            outF.write('\n'.join(cpfr) + '\n')
            cpfr = []
    outF.write('\n'.join(cpfr))
    cpfr,playerPFRCalls,playerPFROpps = [None,None,None]
        
# fold to, call, raise C-bet %
with open('Player.txt') as playerF, open('Round.txt') as roundF, \
        open('GameNum.txt') as gameF, open('Action.txt') as actionF:
    fcb,ccb,rcb = [[]]*3
    playerCBetActions = {}
    playerCBetOpps = {}
    cBettor = ''
    lastG = ''
    cBetSituation = False
    for i,(p,r,g,a) in enumerate(izip(playerF, roundF, gameF, actionF)):
        if not r in ['Preflop','Flop']:
            continue
        if g!=lastG:
            cBettor = ''
        if r=='Preflop':
            if a=='raise':
                cBettor = p
        elif r=='Flop':
            if a=='bet' and p==cBettor:
                cBetSituation = True
            if cBetSituation:
                if p in playerCBetOpps:
                    playerCBetOpps[p] += 1
                else:
                    playerCBetOpps[p] = 1.
                if p in playerCBetActions:
                    if a in playerCBetActions[p]:
                        playerCBetActions[p][a] += 1
                    else:
                        playerCBetActions[p][a] = 1.
                else:
                    playerCBetActions[p] = {a:1.}
with open('Player.txt') as playerF,open('FoldToCBet.txt','ab') as outFoldF, \
        open('CallCBet.txt','ab') as outCallF, open('RaiseCBet.txt','ab') as outRaiseF:
    for i,p in enumerate(playerF):
        fcb.append(playerCBetActions[p]['fold'] / playerCBetOpps[p])
        ccb.append(playerCBetActions[p]['call'] / playerCBetOpps[p])
        rcb.append(playerCBetActions[p]['raise'] / playerCBetOpps[p])
        if i % 10000000 == 0:
            outFoldF.write('\n'.join(fcb) + '\n')
            outCallF.write('\n'.join(ccb) + '\n')
            outRaiseF.write('\n'.join(rcb) + '\n')
            fcb,ccb,rcb = [[]]*3
    outFoldF.write('\n'.join(fcb))
    outCallF.write('\n'.join(ccb))
    outRaiseF.write('\n'.join(rcb))
    fcb,ccb,rcb = [None,None,None]

# fold to, call, raise flop bet %
with open('Player.txt') as playerF, open('Round.txt') as roundF, \
        open('GameNum.txt') as gameF, open('Action.txt') as actionF:
    ffb,cfb,rfb = [[]]*3
    playerFBetActions = {}
    playerFBetOpps = {}
    facingBet = False
    lastG = ''
    for i,(p,r,g,a) in enumerate(izip(playerF, roundF, gameF, actionF)):
        if r=='Flop':
            if g!=lastG:
                facingBet = False
            if facingBet:
                if p in playerFBetOpps:
                    playerFBetOpps[p] += 1
                else:
                    playerFBetOpps[p] = 1
                if p in playerFBetActions:
                    if a in playerFBetActions:
                        playerFBetActions[p][a] += 1
                    else:
                        playerFBetActions[p][a] = 1.
                else:
                    playerFBetActions[p] = {a:1.}
            if a=='bet':
                facingBet = True
with open('Player.txt') as playerF, open('FoldToFlopBet.txt','ab') as outFoldF, \
        open('CallFlopBet.txt','ab') as outCallF, open('RaiseFlopBet.txt','ab') as outRaiseF:
    for i,p in enumerate(playerF):
        ffb.append(playerFBetActions[p]['fold'] / playerFBetOpps[p])
        cfb.append(playerFBetActions[p]['call'] / playerFBetOpps[p])
        rfb.append(playerFBetActions[p]['raise'] / playerFBetOpps[p])
        if i % 10000000 == 0:
            outFoldF.write('\n'.join(ffb) + '\n')
            outCallF.write('\n'.join(cfb) + '\n')
            outRaiseF.write('\n'.join(rfb) + '\n')
            ffb,cfb,rfb = [[]]*3
    outFoldF.write('\n'.join(ffb))
    outCallF.write('\n'.join(cfb))
    outRaiseF.write('\n'.join(rfb))
    ffb,cfb,rfb = [None,None,None]

# net from last hand, rel start stack
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('StartStack.txt') as stackF, open('NetFromLastHand.txt','ab') as outF:
    playerLastStacks = {}
    nets = []
    for i,(p,g,s) in enumerate(izip(playerF, gameF, stackF)):
        s = float(s)
        if p in playerLastStacks:
            nets.append(s - playerLastStacks['Stack'])
            if g!=playerLastStacks['GameNum']:
                playerLastStacks[p] = {'GameNum':g, 'Stack':s}
        else:
            playerLastStacks[p] = {'GameNum':g, 'Stack':s}
        if i % 10000000 == 0:
            outF.write('\n'.join(nets) + '\n')
            nets = []
    outF.write('\n'.join(nets))
    nets,playerLastStacks = [None,None]

# participated in last hand
with open('Player.txt') as playerF, open('GameNum.txt') as gameF, \
        open('Action.txt') as actionF, open('ParticipatedInLastHand.txt') as outF:
    playerPInLastHand = {}
    playerPInCurrentHand = {}
    plh = []
    lastG = ''
    for i,(p,g,a) in enumerate(izip(playerF, gameF, actionF)):
        # first run, populate lastHand with -1's, populate currentHand with actual
        # on same hand, take lastHand, don't update anything
        # on new hand, take currentHand, assign lastHand = currentHand, populate currentHand with actual
        if a!='blind':
            if p in playerPInLastHand:
                if g==lastG:
                    plh.append(playerPInLastHand[p])
                else:
                    plh.append(playerPInCurrentHand[p])
                    playerPInLastHand[p] = playerPInCurrentHand[p]
                    playerPInCurrentHand[p] = a!='fold'
            else:
                playerPInLastHand[p] = -1
                playerPInCurrentHand[p] = a!='fold'
        if i % 10000000 == 0:
            outF.write('\n'.join(plh) + '\n')
            plh = []
        outF.write('\n'.join(plh))
        plh,PlayerPInLastHand,playerPInCurrentHand = [None,None,None]

'''
############################ MERGE COLUMNS TO CSV #############################
os.system('paste -d"," *.txt >> features.csv')

############################ BREAK UP FEATURE SET INTO 8 FILES ################
with open("features.csv") as f:
    rounds = ['Preflop','Flop','Turn','River']
    
    # target feature
    target = ['Action']
    
    # features as dict
    features = pd.read_csv('../../FeatureLists.csv').to_dict('list')
    features = {c: [x for x in features[c] if type(x)==str]
                            for c in features}
    
    # features for each situation; general, fb, flop, turn, river
    sits = [a+b for a,b in product(rounds,['f','t'])]
    
    # combining section features; order of subsets:
    # PFF, PFT, FF, FT, TF, TT, RF, RT
    allFeatureSets = [features['All']]*8
    for i in range(1,8,2):
        allFeatureSets[i] += features['FacingBet']
    for i,r in enumerate(['Flop','Turn','River']):
        for j in [2+i*2, 3+i*2]:
            allFeatureSets[j] += features['UpTo{}Only'.format(r)]
    
    # all files to be written to
    filenames = ['features-PFt', 'features-PFf', 'features-Ft', 'features-Ff',
                 'features-Tt','features-Tf','features-Rt','features-Rf']
    filenames = [fl+".csv" for fl in filenames]
    
    # write headers first (so it is only done once)
    for fs,fn in zip(allFeatureSets, filenames):
        with open(fn,'wb') as fwriteheader:
            csv.DictWriter(fwriteheader, fs).writeheader()
            
    # write actual data to each file
    colnames = f.readline().rstrip().split(',')
    data = [[] for i in xrange(8)]
    for i,line in enumerate(f):
        if i % 50000 == 0 and i!=0:
            for j in range(8):
                with open(filenames[j],'ab') as fwrite:
                    dictWriter = csv.DictWriter(fwrite, allFeatureSets[j])
                    rows = [{k: row[k] for k in allFeatureSets[j]} for row in data[j]]
                    dictWriter.writerows(rows)
            data = [[] for i in xrange(8)]
        elif line[:6]!='Action':
            l = line.rstrip().split(',')
            r = l[2]
            fb = int(l[5])
            listToAddTo = rounds.index(r) * 2 + (1-fb)
            data[listToAddTo].append(dict(zip(colnames, l)))
    for j in range(8):
        with open(filenames[j],'ab') as fwrite:
            dictWriter = csv.DictWriter(fwrite, allFeatureSets[j])
            rows = [{k: row[k] for k in allFeatureSets[j]} for row in data[j]]
            dictWriter.writerows(rows)
    data = [[] for i in xrange(8)]
'''