import os
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
    featureSet['HighestCardOnBoard'] = (cards.max(axis=1, skipna=True) % 13).fillna(0)
    featureSet['RngBoardCardRank'] = (featureSet.HighestCardOnBoard -
                                    cardsRank.min(axis=1, skipna=True)).fillna(0)
    #CallersSinceLastBetOrRaise
    pokerWOB['NumAggActionsRound'] = featureSet.NumAggActionsRound
    featureSet['CallsSinceLastAgg'] = pokerWOB.groupby(['GameNum','Round','NumAggActionsRound']).call.cumsum()
    #EffectiveStackVSActivePlayers
    '''
    ESvsAP = []
    for i,(j,row) in enumerate(pokerWOB.iterrows()):
        windowStart = j
        windowEnd = j
        otherStacks = []
        maxOtherStack = 0
        while windowStart>0 and \
          [poker.iloc[windowStart][c] for c in ['GameNum','Round']] == [row[c] for c in ['GameNum','Round']]:
            r = poker.iloc[windowStart]
            if r['Player']!=row['Player'] and r['Action']!='fold' and r['CurrentStack']>maxOtherStack:
                maxOtherStack = r['CurrentStack']
            windowStart -= 1
        m = poker.shape[0]
        while windowEnd < m and \
          poker.iloc[windowEnd][['GameNum','Round']] == row[['GameNum','Round']]:
            r = poker.iloc[windowEnd]
            if r['Player']!=row['Player'] and r['CurrentStack']>maxOtherStack:
                maxOtherStack = r['CurrentStack']
            windowEnd += 1
        ESvsAP.append(min([maxOtherStack, row['CurrentStack']]))
    featureSet['EffectiveStackVSActivePlayers'] = ESvsAP
    '''
    #EffectiveStackVSAggressor
    featureSet['ESvsAgg'] = (pokerWOB.AggStack >= pokerWOB.CurrentStack) * \
                            pokerWOB.AggStack + \
                            (pokerWOB.AggStack <= pokerWOB.CurrentStack) * \
                            pokerWOB.CurrentStack
    #HighestCardOnBoard
    #InPositionVSActivePlayers
    '''
    ipvap = []
    for i,(_,row) in enumerate(pokerWOB.iterrows()):
        windowStart = pokerWOB.index[i]
        windowEnd = pokerWOB.index[i]
        minOtherRelSeat = 20
        while windowStart>0 and \
          [poker.iloc[windowStart][c] for c in ['GameNum','Round']] == [row[c] for c in ['GameNum','Round']]:
              r = poker.iloc[windowStart]
              if r['Player']!=row['Player'] and r['Action']!='fold' and r['SeatRelDealer'] < minOtherRelSeat:
                  minOtherRelSeat = poker.iloc[windowStart]['SeatRelDealer']
              windowStart -= 1
        while windowEnd<poker.shape[0] and \
          [poker.iloc[windowEnd][c] for c in ['GameNum','Round']] == [row[c] for c in ['GameNum','Round']]:
              r = poker.iloc[windowEnd]
              if r['Player']!=row['Player'] and r['SeatRelDealer'] < minOtherRelSeat:
                  minOtherRelSeat = poker.iloc[windowEnd]['SeatRelDealer']
              windowEnd -= 1
        ipvap.append(int(row['SeatRelDealer'] < minOtherRelSeat))
    featureSet['InPosVsAP'] = ipvap
    '''
    #InPositionVSAggressor
    featureSet['InPosVsAgg'] = (pokerWOB.AggPos > pokerWOB.SeatRelDealer).astype(int)
    #MaxCardsFromSameSuit
    for col in cards:
        cards = cards.join(pd.DataFrame({col+'suit' : cards[col]%4}))
    for i,suit in enumerate(['Clubs','Diamonds','Hearts','Spades']):
        cards = cards.join(pd.DataFrame({'Num'+suit : (cards.iloc[:,5:10]==i).sum(axis=1)}))
    featureSet['MaxCardsFromSameSuit'] = cards.iloc[:,10:].max(axis=1)
    #MaxCardsSameRank
    '''
    boardCols = [[row[c] % 13 if row[c]!='' else '' 
                  for c in ['Board'+str(i) for i in range(1,6)]] 
                  for i,row in pokerWOB.iterrows()]
    featureSet['MaxCardsSameRank'] = [max(row.count(val) 
                                      for val in (set(row) - set('')))
                                      for row in boardCols]
    '''
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
    '''
    npla = []
    n = poker.iloc[0]['NumPlayersLeft']
    for i,(_,row) in enumerate(pokerWOB.iterrows()):
        n -= 1
        if row['GameNum']!=poker.iloc[i-1]['GameNum'] or row['Round']!=poker.iloc[i-1]['Round']:
            n = row['NumPlayersLeft'] - 1
        npla.append(n)
        if row['IsAgg']:
            n = row['NumPlayersLeft'] - 1
    featureSet['PlayersLeftToAct'] = npla
    '''
    #PotOdds
    featureSet['PotOdds'] = pokerWOB.CurrentPot / featureSet.AmtToCall
    #PotSize
    featureSet['PotSize'] = pokerWOB.CurrentPot
    #StackSize
    featureSet['StackSize'] = pokerWOB.CurrentStack
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
    
    boardFeatures = ['AvgBoardCardRank','RngBoardCardRank','HighestCardOnBoard',
                     'MaxCardsFromSameSuit','MaxCardsSameRank','NumFaceCards']
    
    generalFeatures = ['InvestedThisGame','InvestedThisRound','NumPlayersLeftRatio',
                       'NumAggActionsGame','NumAggActionsRound','NumPasActionsGame',
                       'NumPasActionsRound','EffectiveStackVSActivePlayers',
                       'NumBets','NumBetsRound','Button','PlayersLeftToAct', 'PrevAction',
                       'PotSize','StackSize']
                   
    FBFeatures = ['AmtToCall','AllInIfCall','CallersSinceLastAgg','ESvsAgg','InPosVsAgg','PotOdds',
                  'NumFoldsPrev','NumCallsPrev','NumRaisesPrev']
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