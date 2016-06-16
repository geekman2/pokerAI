import os
import gc
import pandas as pd
import numpy as np
from datetime import datetime
from bisect import bisect_left
import csv

# CREATE FEATURE SET
files = ["data/"+f for f in os.listdir('data')]

actions = ['none','deadblind','blind','fold','check','call','bet','raise']

def basicAction(a):
    if a[:3]=='bet':
        return 'bet'
    elif a[:5]=='raise':
        return 'raise'
    else:
        return a

startTime = datetime.now()
for ii,filename in enumerate(files):
    poker = pd.read_csv(filename)
    print "READ IN POKER:", datetime.now() - startTime
    # make seat number relative to dealer button    
    poker['SeatRelDealer'] = np.where(poker.SeatNum > poker.Dealer,
                                        poker.SeatNum - poker.Dealer,
                                        poker.Dealer - poker.SeatNum)
    # action without amount
    poker['BasicAction'] = poker.Action.apply(basicAction)
    poker = poker.join(pd.get_dummies(poker.Action).astype(int))
    # is aggressive or passive action (agg = bet or raise)
    poker['IsAgg'] = (poker.bet | poker['raise']).astype(bool)
    poker['IsPas'] = ~poker.IsAgg
    # make columns to do with chips relative to table stakes
    poker['Amount'] = poker.Amount / poker.BigBlind
    poker['CurrentBet'] = poker.CurrentBet / poker.BigBlind
    poker['CurrentPot'] = poker.CurrentPot / poker.BigBlind
    poker['StartStack'] = poker.StartStack / poker.BigBlind
    poker['CurrentStack'] = poker.CurrentStack / poker.BigBlind
    poker['InvestedThisRound'] = poker.InvestedThisRound / poker.BigBlind
    # WOB = without blinds; remove blind posting actions
    pokerWOB = pd.DataFrame(poker.ix[~((poker.Action=='blind') | (poker.Action=='deadblind'))])
    aggStacks = poker.CurrentStack * pokerWOB.IsAgg
    pokerWOB['AggStack'] = aggStacks.replace(to_replace=0, method='ffill').ix[pokerWOB.index]
    aggPos = poker.SeatRelDealer * pokerWOB.IsAgg
    pokerWOB['AggPos'] = aggPos.replace(to_replace=0, method='ffill').ix[pokerWOB.index]    
    featureSet = pd.DataFrame({'Player': pokerWOB.Player, 'Action': pokerWOB.Action}, index=pokerWOB.index)
    pokerWOB['BetOverPot'] =  pokerWOB.Amount / pokerWOB.CurrentPot
    bins = [0., 0.25, 0.5, 0.75, 1., 2.]
    featureSet['Action'] = [a + str(bins[bisect_left(bins, b)-1])
                            if a=='bet' or a=='raise' else a
                            for a,b in zip(pokerWOB.Action, pokerWOB.BetOverPot)]
    #Round
    featureSet['Round'] = pokerWOB.Round
    #Invested this game
    featureSet['InvestedThisGame'] = pokerWOB.StartStack - pokerWOB.CurrentStack
    #Invested this round
    featureSet['InvestedThisRound'] = pokerWOB.InvestedThisRound
    #Facing a bet
    pokerWOB['FacingBet'] = (pokerWOB.CurrentBet > featureSet.InvestedThisRound).astype(int)
    featureSet['FacingBet'] = pokerWOB.FacingBet
    #NumPlayersLeft
    featureSet['NumPlayersLeftRatio'] = pokerWOB.NumPlayersLeft
    #NumPlayersLeft/NumPlayers ratio
    featureSet['NumPlayersLeftRatio'] = pokerWOB.NumPlayersLeft / pokerWOB.NumPlayers
    #NumAggressiveActions-Game
    featureSet['NumAggActionsGame'] = pokerWOB.groupby('GameNum').IsAgg.cumsum() - pokerWOB.IsAgg
    #NumAggressiveActions-Round
    featureSet['NumAggActionsRound'] = pokerWOB.groupby(['GameNum','Round']).IsAgg.cumsum() - pokerWOB.IsAgg
    #NumPassiveActions-Game
    featureSet['NumPasActionsGame'] = pokerWOB.groupby('GameNum').IsPas.cumsum() - pokerWOB.IsPas
    #NumPassiveActions-Round
    featureSet['NumPasActionsRound'] = pokerWOB.groupby(['GameNum','Round']).IsPas.cumsum() - pokerWOB.IsPas
    #AmountToCall
    featureSet['AmtToCall'] = pokerWOB.CurrentBet - featureSet.InvestedThisRound
    #ToBeAllInIfCall
    featureSet['AllInIfCall'] = ((featureSet.AmtToCall) > pokerWOB.CurrentStack).astype(int)
    #AverageBoardCardRank
    cards = pokerWOB[['Board1','Board2','Board3','Board4','Board5']]
    cardsRank = cards % 13
    cardsSuit = cards % 4
    featureSet['AvgBoardCardRank'] = cardsRank.mean(axis=1, skipna=True).fillna(0)
    #RangeOfBoardCards
    featureSet['HighestCardOnBoard'] = cardsRank.max(axis=1, skipna=True).fillna(0)
    featureSet['RngBoardCardRank'] = (featureSet.HighestCardOnBoard -
                                    cardsRank.min(axis=1, skipna=True)).fillna(0)
    #CallersSinceLastBetOrRaise
    pokerWOB['NumAggActionsRound'] = featureSet.NumAggActionsRound
    featureSet['CallsSinceLastAgg'] = pokerWOB.groupby(['GameNum','Round','NumAggActionsRound']).call.cumsum()
    # get active players for each row
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
    #EffectiveStackVSAggressor
    featureSet['ESvsAgg'] = (pokerWOB.AggStack>=pokerWOB.CurrentStack)*pokerWOB.AggStack + \
                            (pokerWOB.CurrentStack>=pokerWOB.AggStack)*pokerWOB.CurrentStack
    #HighestCardOnBoard
    featureSet['HighestCardOnBoard'] = cardsRank.max(axis=1, skipna=True).fillna(0)
    #InPositionVSActivePlayers
    relevantCols = ['GameNum','Round','Player','Action','SeatRelDealer']
    ipDF = zip(*[poker[c] for c in relevantCols])
    IPbyRow = []
    m = len(ipDF)
    for i,(gameNum,rd,player,action,seat) in enumerate(ipDF):
        ip = []
        windowStart = i
        windowEnd = i
        minOtherSeat = 20
        while windowStart>=0 and esDF[windowStart][:2]==(gameNum,rd):
            r = ipDF[windowStart]
            if r[2]!=player and r[4]<minOtherSeat and r[3]!='fold':
                minOtherSeat = r[4]
            windowStart -= 1
        while windowEnd<m and esDF[windowEnd][:2]==(gameNum,rd):
            row = esDF[windowEnd]
            if row[2]!=player and r[4]<minOtherSeat:
                minOtherSeat = r[4]
            windowEnd += 1
        IPbyRow.append(ip)
    featureSet['InPosition'] = [IPbyRow[i] for i in pokerWOB.index]
    del IPbyRow
    gc.collect()
    #InPositionVSAggressor
    featureSet['InPosVsAgg'] = (pokerWOB.AggPos > pokerWOB.SeatRelDealer).astype(int)
    #MaxCardsSameSuit
    suitCounts = {}
    for s in xrange(4):
        suitCounts[s] = list((cardsSuit==s).sum(axis=1))
    featureSet['MaxCardsSameSuit'] = pd.DataFrame(suitCounts).max(axis=1)
    #MaxCardsSameRank
    rankCounts = {}
    for r in xrange(13):
        rankCounts[r] = list((cardsRank==r).sum(axis=1))
    featureSet['MaxCardsSameRank'] = pd.DataFrame(rankCounts).max(axis=1)
    #NumBets
    pokerWOB['IsBet'] = np.equal(pokerWOB.Action, 'bet').astype(int)
    featureSet['NumBets'] = pokerWOB.groupby('GameNum').IsBet.cumsum()
    #NumBetsRound
    featureSet['NumBetsRound'] = pokerWOB.groupby(['GameNum','Round']).IsBet.cumsum()
    #NumCardsJackOrHigher
    featureSet['NumFaceCards'] = ((cards.iloc[:,:5] % 13) >= 9).sum(axis=1)
    #Button
    featureSet['Button'] = pokerWOB.Dealer
    #MyPreviousAction
    featureSet['PrevAction'] = poker.groupby(['GameNum','Player']).Action.shift(1).ix[pokerWOB.index].fillna('none')
    featureSet['PrevAction'] = [actions.index(x) for x in featureSet.PrevAction]
    #PlayersLeftToAct
    relevantCols = ['GameNum','Round','Player','Action','NumPlayersLeft','IsAgg']
    nplaDF = zip(*[poker[c] for c in relevantCols])
    npla = []
    n = nplaDF[0][-1]
    for i,(gameNum,rd,player,action,numPlayersLeft,isAgg) in enumerate(nplaDF):
        n -= 1
        if gameNum!=nplaDF[i-1][0] or rd!=nplaDF[i-1][1]:
            n = numPlayersLeft - 1
        npla.append(n)
        if isAgg:
            n = numPlayersLeft - 1
    featureSet['PlayersLeftToAct'] = [npla[i] for i in pokerWOB.index]
    del npla
    gc.collect()
    #PotOdds
    featureSet['PotOdds'] = pokerWOB.CurrentPot / featureSet.AmtToCall
    #PotSize
    featureSet['PotSize'] = pokerWOB.CurrentPot
    #NumFolds/Calls/Checks/Bets/Raises
    featureSet['NumFoldsPrev'] = pokerWOB.groupby(['Round','FacingBet','Player']).fold.cumsum()
    featureSet['NumChecksPrev'] = pokerWOB.groupby(['Round','FacingBet','Player']).check.cumsum()
    featureSet['NumCallsPrev'] = pokerWOB.groupby(['Round','FacingBet','Player']).call.cumsum()
    featureSet['NumBetsPrev'] = pokerWOB.groupby(['Round','FacingBet','Player']).bet.cumsum()
    featureSet['NumRaisesPrev'] = pokerWOB.groupby(['Round','FacingBet','Player'])['raise'].cumsum()
    print "FEATURE SET COMPLETE", datetime.now() - startTime
    with open("featuresets/features.csv",'a') as f:
        if ii==0:
            featureSet.to_csv(f, index=False, header=True)
        else:
            featureSet.to_csv(f, index=False, header=False)
    print "FEATURES WRITTEN TO CSV", datetime.now() - startTime

# BREAK UP FEATURE SET INTO 8 FILES
os.chdir('featuresets')
with open("features.csv") as f:
    rounds = ['Preflop','Flop','Turn','River']
    
    # feature sets for different files
    target = ['Action']
    
    # for all subsets
    generalFeatures = ['InvestedThisGame','InvestedThisRound','NumPlayersLeftRatio',
                       'NumAggActionsGame','NumAggActionsRound','NumPasActionsGame',
                       'NumPasActionsRound','EffectiveStack','InPos','NumBets',
                       'NumBetsRound','Button','PlayersLeftToAct', 'PrevAction',
                       'PotSize']
    
    # Cards on the board or not?
    boardFeatures = ['AvgBoardCardRank','RngBoardCardRank','HighestCardOnBoard',
                     'MaxCardsSameSuit','MaxCardsSameRank','NumFaceCards']
                   
    # Facing bet or not?
    FBFeatures = ['AmtToCall','AllInIfCall','CallsSinceLastAgg','ESvsAgg',
                  'InPosVsAgg','PotOdds','NumFoldsPrev','NumCallsPrev','NumRaisesPrev']
    nonFBFeatures = ['NumChecksPrev','NumBetsPrev']
    
    allFeatureSets = [generalFeatures+FBFeatures, generalFeatures+nonFBFeatures]
    allFeatureSets += [generalFeatures+boardFeatures+FBFeatures,
                       generalFeatures+boardFeatures+nonFBFeatures]*3
    allFeatureSets = [['Player'] + target + features for features in allFeatureSets]
    
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