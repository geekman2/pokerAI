import random
from copy import copy
from bisect import bisect_left
import handEstimation
#handEstimation is constantly being reloaded; run once and then comment out

# global variables
cardNumRange = [str(i) for i in range(2,11)] + ['J','Q','K','A']
cardSuitRange = ['d','c','h','s']
deck = [str(i) + str(j) for i in cardNumRange for j in cardSuitRange]

class Game(object):
    stages = ['preflop','postflop','turn','river']
    
    def __init__(self, smallBlind, numPlayers, startStack):
        self.tableSize = numPlayers
        self.names = ['Andy','Bob','Chris','Dennis','Eddie','Fred','Greg','Harris','Ingrid']
        self.startStack = startStack
        self.deck = range(52)
        self.smallBlind = smallBlind
        self.bigBlind = smallBlind*2
        self.board = []
        self.pot = 0
        self.dynamicSeat = 0
        self.button = -1
        self.handNum = 0
        self.currentBet = 0
        self.currentRoundInd = 0
        self.numPlayers = numPlayers
        self.players = [Player(self.startStack, self.names[i], self, i)
                        for i in range(self.numPlayers)]
        self.participatingByStaticSeat = range(numPlayers)
        self.lastRaise = 0
        self.allPots = []
    
    ######################### DEAL HOLE CARDS #################################
    def dealHoleCards(self):
        playerRange = [i % self.numPlayers for i in range(self.button, self.button+self.numPlayers)]
        random.shuffle(self.deck)
        for playerInd in playerRange:
            for i in range(2):
                newCard = self.deck.pop()
                self.players[playerInd].holeCards.append(newCard)
    
    ######################### NEW HAND ########################################
    def newHand(self):
        print "\n------------------------ NEW HAND -------------------------\n"
        #self.deck = [str(i) + str(j) for i in cardNumRange for j in cardSuitRange]
        self.deck = range(52)
        self.participatingByStaticSeat = [p.staticSeat for p in self.players]
        for player in self.players:
            player.handReset()
        self.button = (self.button + 1) % self.tableSize
        print "button: ", self.button
        while self.button not in self.participatingByStaticSeat:
            self.button = (self.button + 1) % self.tableSize
            print "button: ", self.button
        self.staticSeat = copy(self.button)
        self.dynamicSeat = self.participatingByStaticSeat.index(self.button)
        self.board = []
        self.currentRoundInd = 0
        self.pot = 0
        self.allPots = []
        self.lastRaise = 0
        self.handNum += 1
        self.currentBet = self.bigBlind
        self.dealHoleCards()
        self.takeBlinds()
    
    ######################### DEAL STREET #####################################
    def dealStreet(self, street):
        if street=='flop':
            for i in range(3):
                self.board.append(self.deck.pop())
        else:
            self.board.append(self.deck.pop())
        self.currentRoundInd += 1
        self.currentBet = 0
        self.lastRaise = 0
        self.staticSeat = (self.button + 1) % self.tableSize
        while self.staticSeat not in self.participatingByStaticSeat:
            self.staticSeat = (self.staticSeat + 1) % self.tableSize
        self.dynamicSeat = self.participatingByStaticSeat.index(self.staticSeat)
        for player in self.players:
            player.investedThisRound = 0
    
    ######################### EXECUTE ONE PLAYER ACTION #######################
    def executePlayerAction(self):
        player = self.players[self.dynamicSeat]
        decision = player.decideAction()
        if len(decision)==2:
            action, amount = decision
            getattr(player, action)(amount) # get player to call action
        else:
            action = decision
            getattr(player, action)()
        return action
        
    ######################### TAKE BLINDS #####################################
    def takeBlinds(self):
        sbSpot = (self.button + 1) % len(self.players)
        print "small blind: ", sbSpot
        sbPlayer = self.players[sbSpot]
        sbPlayer.payBlind(self.smallBlind)
        
        bbSpot = (self.button + 2) % len(self.players)
        print "big blind: ", bbSpot
        bbPlayer = self.players[bbSpot]
        bbPlayer.payBlind(self.bigBlind)
        
        self.dynamicSeat = (bbSpot + 1) % len(self.players)
        
    ######################## CALC SIDE POTS ###################################
    def calcPots(self):
        newPots = []
        invs = [p.investedThisHand for p in self.players 
                                if p.staticSeat in self.participatingByStaticSeat]
        outInvs = [p.investedThisHand for p in self.players 
                                if not (p.staticSeat in self.participatingByStaticSeat)]
        sui = sorted(list(set(invs))) # Sorted Unique Investments
        sui0 = [0] + sui
        eligible = copy(self.participatingByStaticSeat)
        suiDiffs = [sui0[i+1]-sui0[i] for i in range(len(sui0)-1)]
        for i in range(len(suiDiffs)):
            eligible = [seat for inv,seat in zip(invs,eligible) if inv>=suiDiffs[i]]
            invs = [inv-suiDiffs[i] for inv in invs if inv>=suiDiffs[i]]
            amount = suiDiffs[i] * len(eligible)
            newPots.append({'eligible':eligible, 'amount':amount})
        for inv in outInvs:
            potToInsert = bisect_left(sui, inv)
            newPots[potToInsert]['amount'] += inv
        self.allPots = newPots
        
    ######################## AWARD WINNER #####################################
    def awardWinner(self):
        self.calcPots()
        print "all pots: ", self.allPots
        for p in self.players:
            p.getHandValue()
        playersHands = [(p, p.staticSeat, p.handValue) for p in self.players]
        sortedHands = sorted(playersHands, key = lambda x: x[2])[::-1]
        for pot in self.allPots:
            eligibleHands = [h for h in sortedHands if h[1] in pot['eligible']]
            winners = [h[0] for h in eligibleHands if h[2]==eligibleHands[0][2]]
            winnings = pot['amount'] / len(winners)
            for w in winners:
                w.stack += winnings
            print "POT SIZE: ", pot
            print "WINNERS: ", [w.name for w in winners]
            print "WINNINGS: ", winnings
        
    ###################### PRINT INFO #########################################
    def statusPrint(self):
        print "round: ", [p.investedThisRound for p in self.players if \
                            p.staticSeat in self.participatingByStaticSeat]
        print "stacks: ", [(p.name, p.stack) for p in self.players if \
                            p.staticSeat in self.participatingByStaticSeat]
        print "pot: ", self.pot
        print "all pots: ", self.allPots
        print "bet: ", self.currentBet
        print "board: ", [deck[i] for i in self.board]
        print "your hole cards: ", [deck[i] for i in self.players[self.dynamicSeat].holeCards]
        print "your name: ", self.players[self.dynamicSeat].name
        print "investments: ", [(p.staticSeat, p.investedThisHand) for p in self.players \
                            if p.staticSeat in self.participatingByStaticSeat and p.stack>0]
        print "current round ind: ", self.currentRoundInd
        
    ######################### EXECUTE FULL HAND ###############################
    def executeHand(self):
        self.newHand()
        
        investments = [p.investedThisHand for p in self.players if \
                        p.staticSeat in self.participatingByStaticSeat]
        
        for street in ['preflop','flop','turn','river']:
            if street in ['flop','turn','river']:
                self.dealStreet(street)
                print street.upper() + " DEALT"
            if sum(p.stack>0 for p in self.players if p.staticSeat in self.participatingByStaticSeat) > 1:
                for i in range(self.numPlayers):
                    if self.players[self.dynamicSeat].staticSeat in self.participatingByStaticSeat \
                    and self.players[self.dynamicSeat].stack > 0:
                        self.statusPrint()
                        self.executePlayerAction()
                        self.dynamicSeat = (self.dynamicSeat + 1) % len(self.players)
                        investments = [p.investedThisHand for p in self.players \
                                        if p.staticSeat in self.participatingByStaticSeat and p.stack>0]
                        if len(self.participatingByStaticSeat)==1:
                            print "WINNER: " + self.players[self.participatingByStaticSeat[0]].name + " wins " + str(self.pot)
                            self.players[self.participatingByStaticSeat[0]].stack += self.pot
                            return
                    else:
                        self.dynamicSeat = (self.dynamicSeat + 1) % len(self.players)
                while len(set(investments))>1:
                    if self.dynamicSeat in self.participatingByStaticSeat:
                        self.statusPrint()
                        self.executePlayerAction()
                        self.dynamicSeat = (self.dynamicSeat + 1) % len(self.players)
                        investments = [p.investedThisHand for p in self.players \
                                        if p.staticSeat in self.participatingByStaticSeat and p.stack>0]
                        if len(self.participatingByStaticSeat)==1:
                            print "WINNER: " + self.players[self.participatingByStaticSeat[0]].name + " wins " + str(self.pot)
                            self.players[self.participatingByStaticSeat[0]].stack += self.pot
                            return
                    else:
                        self.dynamicSeat = (self.dynamicSeat + 1) % len(self.players)
            else:
                print "ALL IN: skipping round"
            self.calcPots()
        self.awardWinner()
    
    def betweenHands(self):
        self.players = [p for p in self.players if p.stack>0]
        self.numPlayers = len(self.players)
        
    ######################### RUN FULL GAME ###################################
    def runGame(self):
        while self.numPlayers>1:
            self.executeHand()
            self.betweenHands()
    
        
###############################################################################
########################### NEW CLASS: PLAYER #################################
###############################################################################

class Player(object):
    actions = ['fold','check','call','bet','raise']
    
    def __init__(self, startStack, name, game, staticSeat):
        self.stack = startStack
        self.holeCards = []
        self.name = name
        self.legalActions = Player.actions
        self.investedThisHand = 0
        self.investedThisRound = 0
        self.game = game
        self.staticSeat = staticSeat
        self.handValue = [0,0]
        
    def handReset(self):
        self.holeCards = []
        self.legalActions = Player.actions
        self.investedThisHand = 0
        self.investedThisRound = 0
        
    def updateLegalActions(self):
        investedRound = self.investedThisRound
        allInvestments = [p.investedThisHand for p in self.game.players \
                                            if p.staticSeat in self.game.participatingByStaticSeat]
        if investedRound < self.game.currentBet:
            self.legalActions = ['fold','call','raise']
        elif self.game.currentBet == investedRound == 0:
            self.legalActions = ['check','bet']
        elif len(set(allInvestments))==1:
            if self.game.currentRoundInd==0:
                self.legalActions = ['check','raise']
            else:
                self.legalActions = ['check','bet']
        if self.game.currentBet < self.stack:
            self.legalActions.append("allIn")
        else:
            self.legalActions = [a for a in self.legalActions if a!='raise']
            #self.legalActions.remove('raise')

    ######################### PAY BLIND #######################################
    def payBlind(self, blind):
        if self.stack > blind:
            self.stack -= blind
            self.investedThisHand += blind
            self.investedThisRound += blind
            self.game.pot += blind
        else:
            self.game.pot += self.stack
            self.investedThisHand += self.stack
            self.investedThisRound += self.stack
            self.stack = 0
    
    ######################### ACTION: FOLD#####################################
    def fold_(self):
        self.game.participatingByStaticSeat.remove(self.staticSeat)
        self.holeCards = []
    
    ######################### ACTION: CHECK ###################################
    def check_(self):
        pass
    
    ######################### ACTION: CALL ####################################
    def call_(self):
        maxInvestment = max([p.investedThisRound for p in self.game.players \
                                                if p.staticSeat in self.game.participatingByStaticSeat])
        diff = maxInvestment - self.investedThisRound
        if maxInvestment > self.stack:
            self.investedThisHand += self.stack
            self.investedThisRound = self.stack
            self.game.pot += self.stack
            self.stack = 0
        else:
            self.stack -= diff
            self.investedThisHand += diff
            self.investedThisRound = maxInvestment
            self.game.pot += diff

    ######################### ACTION: BET ######################################
    def bet_(self, amount):
        self.game.currentBet = amount
        self.stack -= amount
        self.investedThisHand += amount
        self.investedThisRound = amount
        self.game.pot += amount
        
    ######################### ACTION: RAISE ###################################
    def raise_(self, raiseTo):
        self.game.lastRaise = raiseTo - self.game.currentBet
        self.game.currentBet = raiseTo
        extra = raiseTo - self.investedThisRound
        self.stack -= extra
        self.investedThisHand += extra
        self.investedThisRound = raiseTo
        self.game.pot += extra
        
    ######################## ACTION: ALLIN ####################################
    def allIn_(self):
        self.bet_(self.stack)
    
    ####################### HAND VALUE ESTIMATION #############################
    def getHandOdds(self):
        return handEstimation.handOdds(self.holeCards, self.game.board, self.game.numPlayers, 5000)
        
    ####################### HAND EVALUATION ###################################
    def getHandValue(self):
        self.handValue = handEstimation.handEval(self.holeCards + self.game.board)
        
    ####################### GET USER INPUT: ACTION ############################
    def decideAction(self):
        self.updateLegalActions()
        toCall = str(min([self.game.currentBet, self.stack]))
        printActions = [a+'-'+toCall if a=='call' else a for a in self.legalActions]
        print "Your available actions are: ", printActions
        while True:
            actionString = raw_input("Choose one, or ask for hand strength: ")
            if actionString=='hand':
                print self.getHandOdds()
            elif actionString == "end":
                raise ValueError
            elif actionString in ["fold", "check", "call", "allIn"]:
                return actionString + "_"
            elif actionString == "bet":
                while True:
                    amount = int(raw_input("Specify amount: "))
                    if amount > self.stack:
                        print "insufficient chips for that bet"
                    elif amount < self.game.bigBlind:
                        print "bet not large enough; must be at least BB"
                    else:
                        return [actionString + "_", amount]            
            elif actionString == "raise":
                while True:
                    raiseTo = int(raw_input("Specify amount to raise to: "))
                    betPlusRaise = self.game.currentBet + self.game.lastRaise
                    if self.game.lastRaise==0 and raiseTo < (self.game.currentBet*2) \
                    or self.game.lastRaise>0 and raiseTo < betPlusRaise:
                        print "insufficient raise"
                    elif raiseTo > self.stack:
                        print "insufficient chips for that raise"
                    else:
                        return [actionString + "_", raiseTo]
            else:
                print "Not a legal action, try again."
                
game1 = Game(10,9,1000)
game1.runGame()