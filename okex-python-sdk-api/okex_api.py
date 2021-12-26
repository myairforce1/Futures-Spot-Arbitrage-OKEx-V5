import okex.account as account
import okex.public as public
import okex.trade as trade
from okex.exceptions import OkexException, OkexAPIException
import key
import time
from mythread import MyThread
from log import fprint
import lang
import asyncio

SLEEP = 0.2
CONFIRMATION = 3


def round_to(number, fraction):
    """返回fraction的倍数
    """
    # 小数点后位数
    ndigits = len('{:f}'.format(fraction - int(fraction))) - 2
    if ndigits > 0:
        return round(int(number / fraction) * fraction, ndigits)
    else:
        return round(int(number / fraction) * fraction)


class OKExAPI:
    """基本OKEx功能类
    """

    def __init__(self, coin: str = None, accountid=3):
        # print('OKExAPI init started')
        self.accountid = accountid
        apikey = key.Key(accountid)
        api_key = apikey.api_key
        secret_key = apikey.secret_key
        passphrase = apikey.passphrase

        if accountid == 3:
            self.accountAPI = account.AccountAPI(api_key, secret_key, passphrase, test=True)
            self.tradeAPI = trade.TradeAPI(api_key, secret_key, passphrase, test=True)
            self.publicAPI = public.PublicAPI(test=True)
        else:
            self.accountAPI = account.AccountAPI(api_key, secret_key, passphrase, False)
            self.tradeAPI = trade.TradeAPI(api_key, secret_key, passphrase, False)
            self.publicAPI = public.PublicAPI()

        self.coin = coin
        if coin:
            self.spot_ID = coin + '-USDT'
            self.swap_ID = coin + '-USDT-SWAP'

            self.exitFlag = False
            self.exist = True

            # 公共-获取现货信息
            # 公共-获取合约信息
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # print('Event loop is running. Call await.')
                    pass
                else:
                    tasks = [self.publicAPI.async_get_specific_instrument('SPOT', self.spot_ID),
                             self.publicAPI.async_get_specific_instrument('SWAP', self.swap_ID)]
                    results = loop.run_until_complete(asyncio.gather(*tasks))
                    self.spot_info: dict = results[0]
                    self.swap_info: dict = results[1]
                # print(f'OKExAPI({self.coin}) init finished')
            except Exception as e:
                print(f'OKExAPI({self.coin}) init error')
                print(e)
                self.exist = False
                fprint(lang.nonexistent_crypto)
        else:
            self.exist = False

    async def __async__init__(self):
        if self.coin:
            try:
                tasks = [self.publicAPI.async_get_specific_instrument('SPOT', self.spot_ID),
                         self.publicAPI.async_get_specific_instrument('SWAP', self.swap_ID)]
                results = await asyncio.gather(*tasks)
                self.spot_info: dict = results[0]
                self.swap_info: dict = results[1]
                # print(f'__async__init__({self.coin}) init finished')
                return self
            except Exception as e:
                print(f'__async__init__({self.coin}) init error')
                print(e)
                self.exist = False
                fprint(lang.nonexistent_crypto)

    def __await__(self):
        return self.__async__init__().__await__()

    async def check_account_level(self):
        level = (await self.accountAPI.get_account_config())['acctLv']
        if level == '1':
            fprint(lang.upgrade_account)
            exit()

    async def check_position_mode(self):
        mode = (await self.accountAPI.get_account_config())['posMode']
        if mode != 'net_mode':
            fprint(lang.position_mode.format(mode))
            await self.accountAPI.set_position_mode('net_mode')
            fprint(lang.change_net_mode)
        mode = (await self.accountAPI.get_account_config())['posMode']
        if mode != 'net_mode':
            fprint(lang.set_mode_fail)
            exit()

    def usdt_balance(self):
        """获取USDT保证金
        """
        data: list = self.accountAPI.get_coin_account('USDT')['details']
        if data:
            return float(data[0]['availEq'])
        else:
            return 0.

    async def async_spot_position(self, coin=None):
        """获取现货余额
        """
        if not coin:
            coin = self.coin
        data: list = (await self.accountAPI.async_get_coin_account(coin))['details']
        if data:
            return float(data[0]['availEq'])
        else:
            return 0.

    def spot_position(self):
        """获取现货余额
        """
        data: list = self.accountAPI.get_coin_account(self.coin)['details']
        if data:
            return float(data[0]['availEq'])
        else:
            return 0.

    async def async_swap_holding(self, swap_ID):
        """获取合约持仓
        """
        if not swap_ID:
            swap_ID = self.swap_ID
        result: list = await self.accountAPI.async_get_specific_position(swap_ID)
        for n in result:
            if n['mgnMode'] == 'isolated':
                return n
        return None

    def swap_holding(self):
        """获取合约持仓
        """
        result: list = self.accountAPI.get_specific_position(self.swap_ID)
        # if len(result) > 1:
        #     fprint(lang.more_than_one_position.format(self.swap_ID))
        #     fprint(result)
        #     exit()
        # else:
        for n in result:
            if n['mgnMode'] == 'isolated':
                return n
        return None

    async def async_swap_position(self, swap_ID=None):
        """获取合约仓位
        """
        if not swap_ID:
            swap_ID = self.swap_ID
        swap_info = await self.publicAPI.async_get_specific_instrument('SWAP', swap_ID)
        contract_val = float(swap_info['ctVal'])
        holding = await self.async_swap_holding(swap_ID)
        if holding and holding['pos']:
            return - float(holding['pos']) * contract_val
        else:
            return 0.

    def swap_position(self):
        """获取合约仓位
        """
        contract_val = float(self.swap_info['ctVal'])
        holding = self.swap_holding()
        if holding and holding['pos']:
            return - float(holding['pos']) * contract_val
        else:
            return 0.

    async def async_swap_balance(self):
        """获取占用保证金
        """
        holding = await self.async_swap_holding(self.swap_ID)
        if holding and holding['margin']:
            return float(holding['margin'])
        else:
            return 0.

    def swap_balance(self):
        """获取占用保证金
        """
        holding = self.swap_holding()
        if holding and holding['margin']:
            return float(holding['margin'])
        else:
            return 0.

    def get_lever(self):
        setting = self.accountAPI.get_leverage(self.swap_ID, 'isolated')
        return int(float(setting['lever']))

    def add_margin(self, transfer_amount):
        """增加保证金

        :param transfer_amount: 划转金额
        :return: 是否成功
        :rtype: bool
        """
        if transfer_amount <= 0:
            return False
        try:
            if self.accountAPI.adjust_margin(instId=self.swap_ID, posSide='net', type='add', amt=transfer_amount):
                fprint(lang.added_margin, transfer_amount, "USDT")
                return True
            else:
                return False
        except OkexAPIException as e:
            fprint(e)
            fprint(lang.transfer_failed)
            if e.code == "58110":
                time.sleep(600)
            return False

    def reduce_margin(self, transfer_amount):
        """减少保证金

        :param transfer_amount: 划转金额
        :return: 是否成功
        :rtype: bool
        """
        if transfer_amount <= 0:
            return False
        try:
            if self.accountAPI.adjust_margin(instId=self.swap_ID, posSide='net', type='reduce', amt=transfer_amount):
                fprint(lang.reduced_margin, transfer_amount, "USDT")
                return True
            else:
                return False
        except OkexAPIException as e:
            fprint(e)
            fprint(lang.transfer_failed)
            if e.code == "58110":
                time.sleep(600)
            return False

    async def get_tickers(self):
        tasks = [self.publicAPI.async_get_specific_ticker(self.spot_ID),
                 self.publicAPI.async_get_specific_ticker(self.swap_ID)]
        return await asyncio.gather(*tasks)

    def parallel_ticker(self):
        """多线程获取现货合约价格
        """
        # 最小延时0.34
        # send = time.time()
        thread1 = MyThread(target=self.publicAPI.get_specific_ticker, args=(self.spot_ID,))
        thread1.start()
        thread2 = MyThread(target=self.publicAPI.get_specific_ticker, args=(self.swap_ID,))
        thread2.start()
        thread1.join()
        thread2.join()
        spot_ticker = thread1.get_result()
        swap_ticker = thread2.get_result()
        # receive = time.time()
        # if receive - send > 0.2:
        #     print("timeout", receive - send)
        del thread1
        del thread2
        return [spot_ticker, swap_ticker]
