"Better" Market Order Trading

Implement a way to enter a buy spot/sell perp order, then close those positions while paying less in fees than you would with market orders

I built the strategy around the FTX API, making use of their pre-built Python package (added a few functions that they didn't have built in). I had started working on a Bybit version due to region restrictions but did not complete, so the main_pybit file can be ignored, however for future iterations I think it could be interesting to explore cross-exchange trading opportunities as certain exchanges offer more favorable fees for makers vs takers.

Strategy Description:
On FTX and in general, Market Makers pay a much lower fee (as low as 0 or even negative if certain conditions are met)
Therefore, we know we want to have at least some legs of our trade that are executed as maker orders to avoid fees & avoid crossing the spread as much as possible
1) make a decision on whether we want to go long spot or long perp based on funding rates
2) enter limit post only orders slightly outside of the current bid/ask, I chose to use 5 bps to ensure our orders are placed/executed as makers
3) after one side of the trade gets filled, cancel the other outstanding order and execute any outstanding size as a market order, will have to pay fees here but want to avoid delta exposure
4) after meeting some specified condition (in this case after 10s, in practice this might be 1hr+ to take advantage of funding, or some other conditions), start the position closing process
5) enter maker orders again just outside the bid/ask
6) after one order is executed, cancel the other and execute at market
7) calculate trade & fee PnL

After running the strategy, run the same process using only market orders to compare PnL/fees paid.

Results:
On average, when using .01 ETH per side (at the time ~$10, $40 total traded), I ended up paying 1.5-2¢ total for the strategy trades vs 3-3.5¢ total when using market orders. This does not include potential funding PnL as for testing purposes the time frame is too short to realize any gains/losses there. This could be further reduced by staking FTT on the platform to get rid of maker fees entirely or even start earning rebates on market making trades. We could improve further by using different exchanges with more favorable fee rates for different order types (ie. BitMEX has maker rebates of 2.5bps for Perps at base tier).

Tradeoffs:
Using a 5bp spread to screen allows for more safety in ensuring our post_only orders won't be cancelled due to chance they would trade through the market, however can cause some slowness in waiting for them to execute
Currently was running into an issue with putting on short spot/margin trades, so have that side disabled and area always running long spot/short perp, however this is more relevant in the case where we are trading around the funding (and is a one line fix when I get it enabled)

To run the code/other files:

```main.py``` is set up to run the strategy on the ETH/USD market with .01 ETH per side, followed by running the trade with market orders

```test.py``` will run unit tests utilizing a mock FTX api that I built

```main_pybit.py``` is the incomplete implementation using the Bybit API
