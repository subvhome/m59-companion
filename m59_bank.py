import os
import json
import re
import logging

logger = logging.getLogger("dashboard")

class BankManager:
    def __init__(self):
        self.balances = {"mainland": 0, "island": 0}
        self.current_char = None
        
        self.re_total = re.compile(r'(.*?) tells you, "(?:Thank you for your deposit\.\s+)?You (?:now )?have (\d+) shillings in your account\."', re.I)
        self.re_withdraw = re.compile(r'(.*?) tells you, "Here are your (\d+) shillings\. Thank you for your business\."', re.I)

    def load_balances(self, char_name):
        """Loads persistent balances for a specific character."""
        if not char_name or char_name == "Unknown":
            return
            
        self.current_char = char_name
        sn = char_name.replace(" ", "_")
        p = f"logs/{sn}_bank.json"
        
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    self.balances = json.load(f)
                    logger.info(f"Bank: Loaded balances for {char_name}: M:{self.balances['mainland']}, I:{self.balances['island']}")
            except Exception as e:
                logger.error(f"Bank: Failed to load balances: {e}")
        else:
            self.balances = {"mainland": 0, "island": 0}

    def save_balances(self):
        """Saves current balances to disk."""
        if not self.current_char or self.current_char == "Unknown":
            return
            
        sn = self.current_char.replace(" ", "_")
        p = f"logs/{sn}_bank.json"
        
        try:
            os.makedirs("logs", exist_ok=True)
            with open(p, "w") as f:
                json.dump(self.balances, f)
        except Exception as e:
            logger.error(f"Bank: Failed to save balances: {e}")

    def process_line(self, line):
        """Parses a chat line for bank messages. Returns True if a balance changed."""
        changed = False
        
        # 1. Check for Total Balance / Deposit Result
        m = self.re_total.search(line)
        if m:
            npc, amount = m.groups()
            bank_type = self._get_bank_type(npc)
            if bank_type:
                new_val = int(amount)
                if self.balances[bank_type] != new_val:
                    self.balances[bank_type] = new_val
                    changed = True
                    logger.info(f"Bank: Update detected from {npc} ({bank_type}): {new_val}")
        
        # 2. Check for Withdrawal
        else:
            m = self.re_withdraw.search(line)
            if m:
                npc, amount = m.groups()
                bank_type = self._get_bank_type(npc)
                if bank_type:
                    withdraw_amt = int(amount)
                    self.balances[bank_type] = max(0, self.balances[bank_type] - withdraw_amt)
                    changed = True
                    logger.info(f"Bank: Withdrawal detected from {npc} ({bank_type}): -{withdraw_amt} (New: {self.balances[bank_type]})")
        
        if changed:
            self.save_balances()
            
        return changed

    def _get_bank_type(self, npc_name):
        """Determines if an NPC belongs to Mainland or Island bank."""
        n = npc_name.lower()
        if "skivlat" in n:
            return "mainland"
        if "huital" in n or "nosak" in n:
            return "island"
        return None
