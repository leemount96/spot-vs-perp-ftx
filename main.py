from audioop import add
import time
import urllib.parse
from dotenv import dotenv_values
from typing import Optional, Dict, Any, List
from xmlrpc.client import Boolean

from requests import Request, Session, Response
import hmac


class FtxClient:
    """
    This class was taken from FTX sample code with a few functions added/removed as needed
    """
    _ENDPOINT = 'https://ftx.com/api/'

    def __init__(self, api_key=None, api_secret=None, subaccount_name=None) -> None:
        self._session = Session()
        self._api_key = api_key
        self._api_secret = api_secret
        self._subaccount_name = subaccount_name

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('GET', path, params=params)

    def _post(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('POST', path, json=params)

    def _delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request('DELETE', path, json=params)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        request = Request(method, self._ENDPOINT + path, **kwargs)
        self._sign_request(request)
        response = self._session.send(request.prepare())
        return self._process_response(response)

    def _sign_request(self, request: Request) -> None:
        ts = int(time.time() * 1000)
        prepared = request.prepare()
        signature_payload = f'{ts}{prepared.method}{prepared.path_url}'.encode(
        )
        if prepared.body:
            signature_payload += prepared.body
        signature = hmac.new(self._api_secret.encode(),
                             signature_payload, 'sha256').hexdigest()
        request.headers['FTX-KEY'] = self._api_key
        request.headers['FTX-SIGN'] = signature
        request.headers['FTX-TS'] = str(ts)
        if self._subaccount_name:
            request.headers['FTX-SUBACCOUNT'] = urllib.parse.quote(
                self._subaccount_name)

    def _process_response(self, response: Response) -> Any:
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        else:
            if not data['success']:
                raise Exception(data['error'])
            return data['result']

    def get_future(self, future_name: str = None) -> dict:
        return self._get(f'futures/{future_name}')

    def get_order_status(self, order_id: str = None) -> List[dict]:
        return self._get(f'orders', {'order_id': order_id})

    def modify_order(
        self, existing_order_id: Optional[str] = None,
        existing_client_order_id: Optional[str] = None, price: Optional[float] = None,
        size: Optional[float] = None, client_order_id: Optional[str] = None,
    ) -> dict:
        assert (existing_order_id is None) ^ (existing_client_order_id is None), \
            'Must supply exactly one ID for the order to modify'
        assert (price is None) or (
            size is None), 'Must modify price or size of order'
        path = f'orders/{existing_order_id}/modify' if existing_order_id is not None else \
            f'orders/by_client_id/{existing_client_order_id}/modify'
        return self._post(path, {
            **({'size': size} if size is not None else {}),
            **({'price': price} if price is not None else {}),
            ** ({'clientId': client_order_id} if client_order_id is not None else {}),
        })

    def place_order(self, market: str, side: str, price: float, size: float, type: str = 'limit',
                    reduce_only: bool = False, ioc: bool = False, post_only: bool = False,
                    client_id: str = None, reject_after_ts: float = None) -> dict:
        return self._post('orders', {
            'market': market,
            'side': side,
            'price': price,
            'size': size,
            'type': type,
            'reduceOnly': reduce_only,
            'ioc': ioc,
            'postOnly': post_only,
            'clientId': client_id,
            'rejectAfterTs': reject_after_ts
        })

    def cancel_order(self, order_id: str) -> dict:
        return self._delete(f'orders/{order_id}')

    def get_fills(self, market: str = None, start_time: float = None,
                  end_time: float = None, min_id: int = None, order_id: int = None
                  ) -> List[dict]:
        return self._get('fills', {
            'market': market,
            'start_time': start_time,
            'end_time': end_time,
            'minId': min_id,
            'orderId': order_id
        })

    def get_borrow_rates(self) -> List[dict]:
        return self._get('spot_margin/borrow_rates')

    def get_lending_rates(self) -> List[dict]:
        return self._get('spot_margin/lending_rates')

    def get_future_stats(self, future_name: str) -> dict:
        return self._get(f'futures/{future_name}/stats')

    def get_single_market(self, market: str = None) -> Dict:
        return self._get(f'markets/{market}')
    
    def get_positions(self, show_avg_price: bool = False) -> List[dict]:
        return self._get('positions', {'showAvgPrice': show_avg_price})
    
    def get_balances(self) -> List[dict]:
        return self._get('wallet/balances')


class DeltaNeutralTrade:
    """
    Takes in an underlier, FTX Client object, & trade size
    """

    def __init__(self, underlier: str, ftx_client: object, trade_size: int) -> None:
        """Initialize Trade object

        Args:
            underlier (str): underlier to be traded 
            ftx_client (object): ftx client object
            trade_size (int): size of trade to be done
        """
        self.underlier = underlier
        self.ftx_client = ftx_client
        self.trade_size = trade_size

    def trade(self) -> float:
        """Entry point to start the delta neutral trade strategy

        Returns:
            float: PnL of executed trades
        """
        # check if we want to long spot or long perp
        print("Checking spot vs perp funding")
        self.long_spot = self.check_spot_vs_perp()  

        # start the opening order process
        print("Initiating opening trade")
        self.initiate_trade(is_opening_trade=True)

        # start monitoring for one side of our trade getting filled     
        print("Starting to monitor for fills")
        self.order_status_monitor(is_opening_trade=True)

        # execute leftover on other trade
        print("Executing remaining opening order")
        self.execute_leftover_order()
        
        print("Waiting for fills")
        time.sleep(2)

        # update opening fills
        print("Updating fills")
        self.update_fills(is_opening_trade=True)

        print("Long Open Fill:")
        print(self.long_open_fill)

        print("Short Open Fill:")
        print(self.short_open_fill)

        # wait for trigger to exit the trade
        print("Waiting for exit condition")
        self.wait_for_exit_condition()  

        # close out of the position and go through same process
        print("Initiating close trade")
        self.initiate_trade(is_opening_trade=False)
        print("Starting to monitor for fills")
        self.order_status_monitor(is_opening_trade=False)
        print("Executing remaining closing order")
        self.execute_leftover_order()

        print("Waiting for fills")
        time.sleep(2)

        print("Updating closing fills")
        self.update_fills(is_opening_trade=False)

        print("Long Close Fill:")
        print(self.long_close_fill)
        print("Short Close Fill:")
        print(self.short_close_fill)

        print("Calculating trade pnl")
        print(self.calc_trade_pnl())
        return self.calc_trade_pnl()
    
    def trade_market_orders(self) -> None:
        # check if we want to long spot or long perp
        print("Checking spot vs perp funding")
        self.long_spot = self.check_spot_vs_perp()  

        # enter market orders
        print("Initiating opening trade")
        self.initiate_trade_market_order(is_opening_trade=True)

        # wait for fills, assuming 1s should be enough time to update     
        print("Waiting for orders to fill")
        time.sleep(2)

        # update opening fills
        print("Updating fills")
        self.update_fills(is_opening_trade=True)

        print("Long Open Fill:")
        print(self.long_open_fill)

        print("Short Open Fill:")
        print(self.short_open_fill)

        # wait for trigger to exit the trade
        print("Waiting for exit condition")
        self.wait_for_exit_condition()  

        # close out of the position and go through same process
        print("Initiating close trade")
        self.initiate_trade_market_order(is_opening_trade=False)

        print("Waiting for fills")
        time.sleep(2)

        print("Updating closing fills")
        self.update_fills(is_opening_trade=False)

        print("Long Close Fill:")
        print(self.long_close_fill)
        print("Short Close Fill:")
        print(self.short_close_fill)

        print("Calculating trade pnl")
        print(self.calc_trade_pnl())

        return self.calc_trade_pnl()

    def initiate_trade(self, is_opening_trade) -> None:
        """Places maker post only orders for making a new trade
        trade can be an opening trade or a closing trade

        Args:
            is_opening_trade (bool): true if opening trade, false if closing
        """
        long_limit = 0
        short_limit = float('inf')

        # True if we are going long spot and opening, or are short spot and closing
        if (self.long_spot and is_opening_trade) or (not self.long_spot and not is_opening_trade):
            self.long_market = self.underlier + "/USD"
            self.short_market = self.underlier + "-PERP"
            long_limit = self.get_spot_quote()[0]
            short_limit = self.get_perp_quote()[1]
        else:
            self.long_market = self.underlier + "-PERP"
            self.short_market = self.underlier + "/USD"
            long_limit = self.get_perp_quote()[0]
            short_limit = self.get_spot_quote()[1]

        #place buy order 5bps below screen bid
        self.long_order = self.ftx_client.place_order(
            self.long_market, "buy", long_limit*.9995, self.trade_size, 'limit', post_only=True)
        
        print("Buy order placed")
        print(self.long_order)

        #place sell order 5bps above screen ask
        self.short_order = self.ftx_client.place_order(
            self.short_market, "sell", short_limit*1.0005, self.trade_size, 'limit', post_only=True)
        
        print("Sell order placed")
        print(self.short_order)

    def initiate_trade_market_order(self, is_opening_trade) -> None:
        """Place opposite sided taker orders

        Args:
            is_opening_trade (bool): true if opening trade, false if closing
        """
        #True if we are going long spot and opening, or are short spot and closing
        if (self.long_spot and is_opening_trade) or (not self.long_spot and not is_opening_trade):
            self.long_market = self.underlier + "/USD"
            self.short_market = self.underlier + "-PERP"
        else:
            self.long_market = self.underlier + "-PERP"
            self.short_market = self.underlier + "/USD"

        self.long_order = self.ftx_client.place_order(
            self.long_market, "buy", None, self.trade_size, 'market')
        
        print("Long order placed")
        print(self.long_order)

        self.short_order = self.ftx_client.place_order(
            self.short_market, "sell", None, self.trade_size, 'market')
        
        print("Short order placed")
        print(self.short_order)

    def order_status_monitor(self, is_opening_trade) -> None:
        """Function to monitor for fills on open maker orders

        Args:
            is_opening_trade (bool): true if opening trade, false if closing

        Raises:
            Exception: Timeout after 100s with no complete fills
        """
        # check status at this time interval
        sleep_time = .1  

        timeout = sleep_time * 1000

        while True:
            
            #get order list and find our long/short orders, None if they've been filled
            order_list = self.ftx_client.get_order_status()
            self.long_order = next((order for order in order_list if order['id'] == self.long_order['id']), None)
            self.short_order = next((order for order in order_list if order['id'] == self.short_order['id']), None)

            # Check if either order has been filled, either None or remainingSize = 0
            if self.long_order is None or self.short_order is None or self.long_order['remainingSize'] == 0 or self.short_order['remainingSize'] == 0:
                print("At least one trade filled, stopping monitoring process")
                break

            timeout -= sleep_time

            if timeout <= 0:
                #cancel orders if we somehow timeout (waiting to process or odd market behavior)
                self.ftx_client.cancel_order(self.long_order['id'])
                print("Long order cancelled")
                self.ftx_client.cancel_order(self.short_order['id'])
                print("Short order cancelled")
                raise Exception("Timeout waiting for order execution")

            time.sleep(sleep_time)

    def execute_leftover_order(self) -> None:
        """Function to execute any leftover size after one of
        our maker orders was filled. Cancels exsiting order
        and places a market order for the remaining size
        """
        #if short order has been filled, execute long order
        if self.short_order is None or self.short_order['remainingSize'] == 0:
            self.ftx_client.cancel_order(self.long_order['id'])
            self.long_order = self.ftx_client.place_order(self.long_market, "buy", None, self.long_order['remainingSize'], 'market')
        elif self.long_order is None or self.long_order['remainingSize'] == 0:
            self.ftx_client.cancel_order(self.short_order['id'])
            self.short_order = self.ftx_client.place_order(self.short_market, "sell", None, self.short_order['remainingSize'], 'market')


    def update_fills(self, is_opening_trade: Boolean) -> None:
        """Update current state with trade fills
        Checks to see if size from latest is expected trade size, otherwise adds the values
        from the previous fill as well (at most we have 2 orders that have filled)
        Args:
            is_opening_trade (Boolean): true if opening trade, false if closing trade
        """

        long_fill = self.process_fills(self.ftx_client.get_fills(self.long_market))
        short_fill = self.process_fills(self.ftx_client.get_fills(self.short_market))

        if is_opening_trade:
            self.long_open_fill = long_fill
            self.short_open_fill = short_fill
        else:  
            #need to swap the order of these because the "long close" is really buying the short market
            self.long_close_fill = short_fill
            self.short_close_fill = long_fill

    def process_fills(self, fills):
        """Function to process list of fills to aggregate all the fills
        for the latest order

        There is a chacne this leads to an issue if we get a partial fill on the maker
        order, then cancel and enter new market order given they would have differ orderIds, 
        however that case is unlikely and will be revisted in future work

        Args:
            fills: list of trade fills

        Returns:
            fill: aggregated fill of the latest order
        """
        base_fill = fills.pop(0)
        additional_fill = fills.pop(0)

        #continue popping fills until we hit an orderId that is different from the latest order
        while(additional_fill['orderId'] == base_fill['orderId']):
            base_fill['price'] = (base_fill['price'] * base_fill['size'] + additional_fill['price'] * additional_fill['size'])/(base_fill['size'] + additional_fill['size'])
            base_fill['size'] += additional_fill['size']
            base_fill['fee'] += additional_fill['fee']
            additional_fill = fills.pop(0)

        return base_fill        


    def wait_for_exit_condition(self) -> None:
        """
        Function to define our exit condition for the trade
        For now, we wait 1 second then exit

        In the future, this might include waiting for an amount of funding to accrue (>1hr),
        waiting on certain conditions around spreads, etc

        Returns:
            None
        """
        time.sleep(10)
        return

    def calc_trade_pnl(self) -> float:
        """Calculate cumulative trade pnl

        Returns:
            float: total trade pnl
        """
        long_trade_pnl = (self.long_close_fill['price'] - self.long_open_fill['price']) * self.long_open_fill['size']
        long_fee_pnl = self.long_open_fill['fee'] + self.long_close_fill['fee']
        short_trade_pnl = (self.short_open_fill['price'] - self.short_close_fill['price']) * self.short_open_fill['size']
        short_fee_pnl = self.short_open_fill['fee'] + self.short_close_fill['fee']

        return (long_trade_pnl - long_fee_pnl + short_trade_pnl - short_fee_pnl)

    def check_spot_vs_perp(self) -> Boolean:
        """Function to check perp funding rates vs
        spot market borrow/lend rates to determine if
        we should go long spot/short perp or short spot/long perp

        Returns: 
            Boolean: true if long spot, false if short spot
        """
        spot_borrow = self.get_spot_borrow_rate()
        spot_lend = self.get_spot_lending_rate()
        perp_funding = self.get_perp_funding_rate()

        # assume we can lend asset, pay funding on the perp
        long_spot_funding_pnl = self.trade_size * (spot_lend + perp_funding)

        # need to pay to borrow asset to short, posisbly receive funding on perp
        short_spot_funding_pnl = self.trade_size * (-1 * perp_funding - spot_borrow)
        
        return True # Having an issue shorting spot, so defaulting to long spot
        
        # return long_spot_funding_pnl > short_spot_funding_pnl

    def get_spot_borrow_rate(self) -> float:
        """Get current spot borrow rate for self.underlier

        Returns:
            float: borrow rate
        """
        borrow_list = self.ftx_client.get_borrow_rates()

        #returned object is a list of dictionaries, convert it into a readable dict
        borrow_dict = {x['coin']: [x['previous'], x['estimate']] for x in borrow_list}

        #0 index is prev funding, 1 index is upcoming funding which is what we care about
        return borrow_dict[self.underlier][1]

    def get_spot_lending_rate(self) -> float:
        """Get current spot lending rate for self.underlier

        Returns:
            float: lending rate
        """
        lending_list = self.ftx_client.get_lending_rates()

        lending_dict = {x['coin']: [x['previous'], x['estimate']] for x in lending_list}

        return lending_dict[self.underlier][1]

    def get_perp_funding_rate(self) -> float:
        """Get current perp funding rate for self.underlier

        Returns:
            float: funding rate
        """
        return self.ftx_client.get_future_stats(self.underlier + "-PERP")['nextFundingRate']

    def get_spot_quote(self):
        """Get current bid/ask spot market for self.underlier

        Returns:
            tuple containing current bid & ask
        """
        spot_market = self.ftx_client.get_single_market(self.underlier + "/USD")
        return (spot_market['bid'], spot_market['ask'])

    def get_perp_quote(self):
        """Get current bid/ask perp market for self.underlier

        Returns:
            tuple containing current bid & ask
        """
        perp_market = self.ftx_client.get_future(self.underlier + "-PERP")
        return (perp_market['bid'], perp_market['ask'])

config = dotenv_values(".env")

FTX_API_KEY = config['FTX_API_KEY']
FTX_API_SECRET = config['FTX_API_SECRET']
SUBACCOUNT_NAME=config['SUBACCOUNT_NAME']

ftx_client = FtxClient(api_key=FTX_API_KEY, api_secret=FTX_API_SECRET, subaccount_name=SUBACCOUNT_NAME)
trade_size = .01
trade_object = DeltaNeutralTrade("ETH", ftx_client, trade_size)

# print(ftx_client.get_balances())
# print(ftx_client.get_positions())

# print(ftx_client.place_order("ETH/USD", "sell", None, .06, 'market'))
# print(ftx_client.place_order("ETH-PERP", "buy", None, .05, 'market'))

# print(ftx_client.place_order("ETH/USD", "buy", None, .01, 'market'))
# print(ftx_client.place_order("ETH-PERP", "sell", None, .01, 'market'))


print("Running strategy")
strategy_pnl = trade_object.trade()
print("Running market orders only")
market_order_pnl = trade_object.trade_market_orders()

print("Results:")
print("Strategy PnL: " + str(round(strategy_pnl, 5)))
print("Market Order PnL: " + str(round(market_order_pnl, 5)))