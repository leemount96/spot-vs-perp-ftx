from ast import Del
import time
import urllib.parse
from dotenv import dotenv_values
from typing import Optional, Dict, Any, List
from xmlrpc.client import Boolean, boolean
from pybit import usdt_perpetual, spot, inverse_futures

from requests import Request, Session, Response
import hmac


class BybitClient:
    """
    This class was taken from FTX sample code with a few functions added/removed as needed
    """
    _ENDPOINT = 'https://api.bybit.com'

    def __init__(self, api_key=None, api_secret=None, subaccount_name=None) -> None:
        self._session = usdt_perpetual.HTTP(
            endpoint=self._ENDPOINT,
            api_key=api_key,
            api_secret=api_secret
        )
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
        self._session = usdt_perpetual.HTTP(
            endpoint=self._ENDPOINT,
            api_key=self._api_key,
            api_secret=self._api_secret
        )
        market = self._session.latest_information_for_symbol(symbol=future_name)['result'][0]
        return {'bid':float(market['bid_price']), 'ask':float(market['ask_price'])}

    def get_order_status(self, symbol:str, order_id: str = None, is_perp = False) -> dict:
        order = None
        if is_perp:
            self._session = usdt_perpetual.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            try: #try to check order, if error then order has filled
                order = self._session.query_active_order(symbol=symbol, order_id=order_id)['result']
                order['remainingSize'] = float(order['qty']) - float(order['cum_exec_qty'])
            except:
                return None
        else:
            self._session = spot.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            try:
                order = self._session.query_active_order(symbol=symbol, order_id=order_id)['result'][0]
                order['remainingSize'] = float(order['origQty']) - float(order['executedQty'])
            except:
                return None

        order['id'] = order_id
        return order

    def modify_order(
        self, symbol: str, existing_order_id: Optional[str] = None,
        existing_client_order_id: Optional[str] = None, price: Optional[float] = None,
        size: Optional[float] = None, client_order_id: Optional[str] = None, is_perp = False
    ) -> dict:
        print(symbol, is_perp)
        if is_perp:
            self._session = usdt_perpetual.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            try:
                new_id = self._session.replace_active_order(symbol=symbol, order_id=existing_order_id, p_r_price=price)['result']['order_id']
            except:
                return self.get_order_status(symbol=symbol, order_id=existing_order_id, is_perp=is_perp)
        else:
            self._session = spot.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            cancelled_order = self._session.cancel_active_order(symbol=symbol, order_id=existing_order_id)['result']['order_id']


            return self.get_order_status(symbol=symbol, order_id=existing_order_id, is_perp=is_perp)


    def place_order(self, market: str, side: str, price: float, size: float, type: str = 'Limit',
                    reduce_only: bool = False, ioc: bool = False, post_only: bool = False,
                    client_id: str = None, reject_after_ts: float = None, is_perp = False) -> dict:
        order = None
        if is_perp:
            self._session = usdt_perpetual.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            order = self._session.place_active_order(side=side, symbol=market, order_type=type, qty=size, price=price, time_in_force="GoodTillCancel", close_on_trigger=False, reduce_only=False)
            return self.get_order_status(symbol=market, order_id=order['result']['order_id'], is_perp=is_perp)
        else:
            self._session = spot.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            order = self._session.place_active_order(side=side, symbol=market, type=type, qty=size, price=price, time_in_force="GoodTillCancel")
            return self.get_order_status(symbol=market, order_id=order['result']['orderId'], is_perp=is_perp)

    def cancel_order(self, order_id: str, is_perp=False) -> dict:
        return self._delete(f'orders/{order_id}')

    def get_fills(self, market: str = None, start_time: float = None,
                  end_time: float = None, min_id: int = None, order_id: int = None, is_perp = False
                  ) -> List[dict]:
        if is_perp:
            self._session = usdt_perpetual.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            position = self._session.my_position(symbol=market)
            print(position)
            return [{'price': position['entry_price'], 'size': position['size'], 'fee':0}]
        else:
            self._session = spot.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
            
            position = self._session.my_position(symbol=market)
            print(position)
            return [{'price': position['entry_price'], 'size': position['size'], 'fee':0}]

    def get_borrow_rates(self) -> List[dict]:
        return self._get('spot_margin/borrow_rates')

    def get_lending_rates(self) -> List[dict]:
        return self._get('spot_margin/lending_rates')

    def get_future_stats(self, future_name: str) -> dict:
        self._session = usdt_perpetual.HTTP(
            endpoint=self._ENDPOINT,
            api_key=self._api_key,
            api_secret=self._api_secret
        )
        market = self._session.latest_information_for_symbol(symbol=future_name)['result'][0]
        return {'nextFundingRate':float(market['predicted_funding_rate'])}

    def get_single_market(self, market: str = None) -> Dict:
        self._session = spot.HTTP(
            endpoint=self._ENDPOINT,
            api_key=self._api_key,
            api_secret=self._api_secret
        )
        market = self._session.latest_information_for_symbol(symbol=market, spot=True)['result']
        return {'bid':float(market['bestBidPrice']), 'ask':float(market['bestAskPrice'])}

    def get_balance(self, market:str):
        return self._session.get_wallet_balance(coin=market)
    
    def query_symbol(self, is_perp):
        if is_perp:
            self._session = usdt_perpetual.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
        else:
            self._session = spot.HTTP(
                endpoint=self._ENDPOINT,
                api_key=self._api_key,
                api_secret=self._api_secret
            )
        return self._session.query_symbol()

class DeltaNeutralTrade:
    """
    Class to handle the delta neutral trading strategy
    Takes in an underlier, FTX Client object, trade size, and market order price bump
    """

    def __init__(self, underlier: str, ftx_client: object, trade_size: int, market_order_price_bump: float) -> None:
        """Initialize Trade object

        Args:
            underlier (str): underlier to be traded 
            ftx_client (object): ftx client object
            trade_size (int): size of trade to be done
            market_order_price_bump (int): bump for modifying limit order to "market" order
        """
        self.underlier = underlier
        self.ftx_client = ftx_client
        self.trade_size = trade_size
        self.market_order_price_bump = market_order_price_bump

    def trade(self) -> float:
        """Entry point to start the delta neutral trade strategy

        Returns:
            float: PnL of executed trades
        """
        # check if we want to long spot or long perp
        self.long_spot = self.check_spot_vs_perp()  

        # start the opening order process
        self.initiate_trade(is_opening_trade=True)

        # start monitoring for one side of our trade getting filled     
        self.order_status_monitor(is_opening_trade=True)

        # execute leftover on other trade
        self.execute_leftover_order(is_opening_trade=True)

        # update opening fills
        self.update_fills(is_opening_trade=True)

        # wait for trigger to exit the trade
        self.wait_for_exit_condition()  

        # close out of the position and go through same process
        self.initiate_trade(is_opening_trade=False)
        self.order_status_monitor(is_opening_trade=False)
        self.execute_leftover_order(is_opening_trade=False)
        self.update_fills(is_opening_trade=False)

        return self.calc_trade_pnl()

    def initiate_trade(self, is_opening_trade) -> None:
        """Places maker post only orders for making a new trade
        trade can be an opening trade or a closing trade

        Args:
            is_opening_trade (bool): true if opening trade, false if closing
        """
        long_limit = 0
        short_limit = float('inf')
        self.long_market = self.underlier + "USDT"
        self.long_market_is_perp = False
        self.short_market = self.underlier + "USDT"
        self.short_market_is_perp = False

        # True if we are going long spot and opening, or are short spot and closing
        if (self.long_spot and is_opening_trade) or (not self.long_spot and not is_opening_trade):
            long_limit = self.get_spot_quote()[0]
            short_limit = self.get_perp_quote()[1]
            self.short_market_is_perp = True
        else:
            long_limit = self.get_perp_quote()[0]
            short_limit = self.get_spot_quote()[1]
            self.long_market_is_perp = True

        # might need to check trade size here for closing trades if market has moved
        long_trade_size = self.trade_size if is_opening_trade else self.long_open_fill['size']
        short_trade_size = self.trade_size if is_opening_trade else self.short_open_fill['size']
        
        self.long_order = self.ftx_client.place_order(
            self.long_market, "Buy", long_limit, long_trade_size, 'Limit', post_only=True, is_perp=self.long_market_is_perp)
        self.short_order = self.ftx_client.place_order(
            self.short_market, "Sell", short_limit, short_trade_size, 'Limit', post_only=True, is_perp=self.short_market_is_perp)

    def order_status_monitor(self, is_opening_trade) -> None:
        """Function to monitor for fills on open maker orders

        Args:
            is_opening_trade (bool): true if opening trade, false if closing

        Raises:
            Exception: Timeout after 100s with no complete fills
        """
        # check status at this time interval
        sleep_time = 1  

        timeout = sleep_time * 100

        while True:
            # Check if either order has been filled
            if self.long_order is None or self.short_order is None:
                break

            self.long_order = self.ftx_client.get_order_status(self.long_market,
                self.long_order["id"], is_perp=self.long_market_is_perp)
            self.short_order = self.ftx_client.get_order_status(self.short_market,
                self.short_order["id"], is_perp=self.short_market_is_perp)


            timeout -= sleep_time

            if timeout == 0:
                #cancel orders if we somehow timeout (waiting to process or odd market behavior)
                self.ftx_client.cancel_order(self.long_order['id'], is_perp=self.long_market_is_perp)
                self.ftx_client.cancel_order(self.short_order['id'], is_perp=self.short_market_is_perp)
                raise Exception("Timeout waiting for order execution")

            time.sleep(sleep_time)

    def execute_leftover_order(self, is_opening_trade: Boolean) -> None:
        """Function to execute any leftover size after one of
        our maker orders was filled. Places a market order for
        the remaining size and waits for it to fill

        Args:
            is_opening_trade (Boolean): true if opening trade, false if closing
        """
        
        long_limit = 0
        short_limit = float('inf')

        # True if we are going long spot and opening, or are short spot and closing
        if (self.long_spot and is_opening_trade) or (not self.long_spot and not is_opening_trade):
            long_limit = round(self.get_spot_quote()[0] * (1 + self.market_order_price_bump),2)

            short_limit = round(self.get_perp_quote()[1] * (1 - self.market_order_price_bump),2)
        else:
            long_limit = round(self.get_perp_quote()[0] * (1 + self.market_order_price_bump),2)

            short_limit = round(self.get_spot_quote()[1] * (1 - self.market_order_price_bump),2)

        while self.short_order is not None or self.long_order is not None:
            if self.short_order is not None:
                # use modifies as it condenses the cancel + resend
                # not sure if this will change the postOnly param, unclear in docs
                self.short_order = self.ftx_client.modify_order(self.short_market,
                    existing_order_id=self.short_order['id'], price=short_limit, is_perp=self.short_market_is_perp)

            elif self.long_order is not None:
                self.long_order = self.ftx_client.modify_order(self.long_market,
                    existing_order_id=self.long_order['id'], price=long_limit, is_perp=self.long_market_is_perp)

            # allow some time for the order to process so we don't send multiple
            time.sleep(2)

    def update_fills(self, is_opening_trade: Boolean) -> None:
        """Update current state with trade fills

        Args:
            is_opening_trade (Boolean): true if opening trade, false if closing trade
        """
        if is_opening_trade:
            self.long_open_fill = self.ftx_client.get_fills(
                self.long_market, is_perp=self.long_market_is_perp)[-1]
            self.short_open_fill = self.ftx_client.get_fills(
                self.short_market, is_perp=self.short_market_is_perp)[-1]
        else:  
            #need to swap the order of these because the "long close" is really buying the short market
            self.long_close_fill = self.ftx_client.get_fills(
                self.short_market, is_perp=self.short_market_is_perp)[-1]
            self.short_close_fill = self.ftx_client.get_fills(
                self.long_market, is_perp=self.long_market_is_perp)[-1]

    def wait_for_exit_condition(self) -> None:
        """
        Function to define our exit condition for the trade
        For now, we wait 1 second then exit

        In the future, this might include waiting for an amount of funding to accrue (>1hr),
        waiting on certain conditions around spreads, etc

        Returns:
            None
        """
        time.sleep(1)
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
        
        return long_spot_funding_pnl > short_spot_funding_pnl

    def get_spot_borrow_rate(self) -> float:
        """Get current spot borrow rate for self.underlier
        For Bybit testing, we are going to return 0
        Returns:
            float: borrow rate
        """
        return 0

    def get_spot_lending_rate(self) -> float:
        """Get current spot lending rate for self.underlier
        For Bybit testing, we are going to return 0
        Returns:
            float: lending rate
        """
        return 0

    def get_perp_funding_rate(self) -> float:
        """Get current perp funding rate for self.underlier

        Returns:
            float: funding rate
        """
        return self.ftx_client.get_future_stats(self.underlier + "USDT")['nextFundingRate']

    def get_spot_quote(self):
        """Get current bid/ask spot market for self.underlier

        Returns:
            tuple containing current bid & ask
        """
        spot_market = self.ftx_client.get_single_market(
            self.underlier + "USDT")
        return (spot_market['bid'], spot_market['ask'])

    def get_perp_quote(self):
        """Get current bid/ask perp market for self.underlier

        Returns:
            tuple containing current bid & ask
        """
        perp_market = self.ftx_client.get_future(self.underlier + "USDT")
        return (perp_market['bid'], perp_market['ask'])

config = dotenv_values(".env")

BYBIT_API_KEY = config['BYBIT_API_KEY']
BYBIT_API_SECRET = config['BYBIT_API_SECRET']

bybit_client = BybitClient(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

trade = DeltaNeutralTrade("ETH", bybit_client, .01, .05)
trade.trade()

# bid_price = bybit_client.get_single_market("ETHUSDT")['bid']

# order = bybit_client.place_order("ETHUSDT", "BUY", bid_price-10, .01, is_perp=False)
# print(order)
# modifiedOrder = bybit_client.modify_order("ETHUSDT", order['id'], price=bid_price-15, is_perp=False)
# print(modifiedOrder)