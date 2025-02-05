import threading
import time
import json
import datetime
import requests
import os
from colorama import Fore, Style, init
from tabulate import tabulate
from tqdm import tqdm
import signal

init(autoreset=True)

API_URL = "https://kaleidofinance.xyz/api/testnet"

class KaleidoMiningBot:
    def __init__(self, wallet, bot_index):
        self.wallet = wallet
        self.bot_index = bot_index
        self.current_earnings = {"total": 0, "pending": 0, "paid": 0}
        self.mining_state = {"isActive": False, "startTime": None}
        self.referral_bonus = 0
        self.stats = {"hashrate": 75.5, "powerUsage": 120}
        self.session_file = f"session_{wallet}.json"
        self.session = requests.Session()

    def load_session(self):
        if os.path.exists(self.session_file):
            with open(self.session_file, "r") as file:
                session = json.load(file)
                self.mining_state["startTime"] = session["startTime"]
                self.current_earnings = session["earnings"]
                self.referral_bonus = session.get("referralBonus", 0)
                print(Fore.GREEN + f"[Wallet {self.bot_index}] Session loaded successfully.")
                return True
        return False

    def save_session(self):
        session_data = {
            "startTime": self.mining_state["startTime"],
            "earnings": self.current_earnings,
            "referralBonus": self.referral_bonus,
        }
        with open(self.session_file, "w") as file:
            json.dump(session_data, file, indent=2)

    def retry_request(self, request_fn, operation_name):
        while True:
            try:
                return request_fn()
            except requests.RequestException as e:
                if isinstance(e, requests.exceptions.SSLError) or isinstance(e, requests.exceptions.ConnectionError):
                    print(Fore.RED + f"[{operation_name}] Failed connected. Please wait to connect again. Error: {e}")
                else:
                    print(Fore.YELLOW + f"[{operation_name}] Error occurred: {e}. Retrying...")
                time.sleep(1)

    def initialize(self):
        print(Fore.CYAN + f"\n🚀 [Wallet {self.bot_index}] Initializing mining...")
        response = self.retry_request(lambda: self.session.get(f"{API_URL}/check-registration?wallet={self.wallet}"), "Registration Check")

        if not response or not response.json().get("isRegistered"):
            print(Fore.RED + f"[Wallet {self.bot_index}] Wallet not registered!")
            return

        if not self.load_session():
            user_data = response.json()["userData"]
            self.referral_bonus = user_data.get("referralBonus", 0)
            self.current_earnings["total"] = self.referral_bonus
            self.mining_state["startTime"] = time.time()

        self.mining_state["isActive"] = True
        print(Fore.GREEN + f"[Wallet {self.bot_index}] Mining started!")
        self.start_mining_loop()

    def calculate_earnings(self):
        time_elapsed = time.time() - self.mining_state["startTime"]
        return (self.stats["hashrate"] * time_elapsed * 0.0001) * (1 + self.referral_bonus)

    def update_balance(self, final_update=False):
        new_earnings = self.calculate_earnings()
        payload = {
            "wallet": self.wallet,
            "earnings": {
                "total": self.current_earnings["total"] + new_earnings,
                "pending": 0 if final_update else new_earnings,
                "paid": self.current_earnings["paid"] + new_earnings if final_update else self.current_earnings["paid"],
            }
        }

        response = self.retry_request(lambda: self.session.post(f"{API_URL}/update-balance", json=payload), "Balance Update")

        if response and response.json().get("success"):
            self.current_earnings["total"] += new_earnings
            self.current_earnings["pending"] = 0 if final_update else new_earnings
            self.save_session()
            self.log_status()

    def log_status(self):
        uptime = str(datetime.timedelta(seconds=int(time.time() - self.mining_state["startTime"])))

        table_data = [
            ["🔹 Wallet", f"{Fore.CYAN}{self.wallet}{Style.RESET_ALL}"],
            ["⏳ Uptime", f"{Fore.YELLOW}{uptime}{Style.RESET_ALL}"],
            ["⚡ Hashrate", f"{Fore.GREEN}{self.stats['hashrate']} MH/s{Style.RESET_ALL}"],
            ["💰 Total Earned", f"{Fore.CYAN}{self.current_earnings['total']:.8f} KLDO{Style.RESET_ALL}"],
            ["⌛ Pending", f"{Fore.YELLOW}{self.current_earnings['pending']:.8f} KLDO{Style.RESET_ALL}"],
            ["✅ Paid", f"{Fore.GREEN}{self.current_earnings['paid']:.8f} KLDO{Style.RESET_ALL}"],
            ["🎁 Referral Bonus", f"{Fore.MAGENTA}{self.referral_bonus * 100:.1f}%{Style.RESET_ALL}"],
        ]

        print(Fore.YELLOW + "\n📊 === [ Mining Status ] ===")
        print(tabulate(table_data, tablefmt="fancy_grid"))

    def start_mining_loop(self):
        while self.mining_state["isActive"]:
            for _ in tqdm(range(30), desc=f"⛏️  [Mining Wallet {self.bot_index}]", bar_format="{l_bar}{bar} {remaining}"):
                time.sleep(1)
            self.update_balance()

    def stop(self):
        self.mining_state["isActive"] = False
        self.update_balance(final_update=True)
        self.save_session()
        print(Fore.RED + f"[Wallet {self.bot_index}] Mining stopped.")
        return self.current_earnings["paid"]

class MiningCoordinator:
    def __init__(self):
        self.bots = []
        self.is_running = False

    def load_wallets(self):
        if not os.path.exists("wallets.txt"):
            print(Fore.RED + "❌ No wallets.txt found!")
            return []
        with open("wallets.txt", "r") as file:
            return [line.strip() for line in file.readlines() if line.startswith("0x")]

    def start(self):
        if self.is_running:
            print(Fore.YELLOW + "⚠️  Mining coordinator is already running!")
            return

        self.is_running = True
        print(Fore.BLUE + "\n🚀 Starting mining...")

        wallets = self.load_wallets()
        if not wallets:
            print(Fore.RED + "❌ No valid wallets found!")
            return

        print(Fore.GREEN + f"✅ Loaded {len(wallets)} wallets\n")

        self.bots = [KaleidoMiningBot(wallet, i + 1) for i, wallet in enumerate(wallets)]

        threads = []
        for bot in self.bots:
            thread = threading.Thread(target=bot.initialize)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        signal.signal(signal.SIGINT, self.shutdown)

    def shutdown(self, sig, frame):
        print(Fore.YELLOW + "\n⏳ Shutting down miners...")
        total_paid = sum(bot.stop() for bot in self.bots)
        print(Fore.GREEN + f"\n💰 Total Paid: {total_paid:.8f} KLDO\n")
        exit()

if __name__ == "__main__":
    coordinator = MiningCoordinator()
    coordinator.start()
