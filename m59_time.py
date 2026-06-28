import time
from datetime import datetime
import os
import sys

# --- FIXED SERVER ALIGNMENT CONSTANT ---
# Aligns the universal Unix timeline with Server 101's internal engine loop.
# This is identical for all players globally.
# Adjusted by +3600s to correct the 12-hour day/night shift.
ALIGNMENT_OFFSET = -300  
REAL_SECONDS_PER_GAME_DAY = 7200 
REAL_SECONDS_PER_GAME_HOUR = 300 

def get_game_time(current_unix_time=None):
    """Calculates game hour (24h), minute, second, and environmental state."""
    if current_unix_time is None:
        current_unix_time = int(time.time())
    adjusted_time = current_unix_time + ALIGNMENT_OFFSET

    # Compute day and hour boundaries
    seconds_into_game_day = adjusted_time % REAL_SECONDS_PER_GAME_DAY
    game_hour_24 = seconds_into_game_day // REAL_SECONDS_PER_GAME_HOUR

    # Compute fractional minutes and seconds inside the 5-minute block
    seconds_into_game_hour = seconds_into_game_day % REAL_SECONDS_PER_GAME_HOUR
    percentage_of_hour = seconds_into_game_hour / float(REAL_SECONDS_PER_GAME_HOUR)
    
    total_game_minutes = percentage_of_hour * 60.0
    game_minute = int(total_game_minutes)
    game_second = int((total_game_minutes - game_minute) * 60)

    # Smart countdown formatting (Minutes + Seconds remaining until tick)
    seconds_left = REAL_SECONDS_PER_GAME_HOUR - seconds_into_game_hour
    minutes_left = seconds_left // 60
    seconds_left_remainder = seconds_left % 60

    if minutes_left > 0:
        countdown_str = f"{minutes_left}m {seconds_left_remainder:02d}s"
    else:
        countdown_str = f"{seconds_left_remainder}s"

    # Evaluate environmental world state based on game hour rules
    if 6 <= game_hour_24 < 20:
        state = "☀️"
        state_str = "Daytime ☀️"
    elif game_hour_24 == 5 or game_hour_24 == 19:
        state = "🌅"
        state_str = "Dawn/Dusk Transition 🌅"
    else:
        state = "🌙"
        state_str = "Nighttime 🌙"

    return {
        "hour_24": game_hour_24,
        "minute": game_minute,
        "second": game_second,
        "state_emoji": state,
        "state_desc": state_str,
        "countdown": countdown_str
    }

def format_game_time(info, use_24h=True):
    """Formats the game time info dict into a readable 12h or 24h string."""
    h = info["hour_24"]
    m = info["minute"]
    s = info["second"]
    emoji = info["state_emoji"]
    
    if use_24h:
        return f"{h:02d}:{m:02d}:{s:02d} {emoji}"
    else:
        if h == 0:
            h12 = 12
            ampm = "AM"
        elif h == 12:
            h12 = 12
            ampm = "PM"
        elif h > 12:
            h12 = h - 12
            ampm = "PM"
        else:
            h12 = h
            ampm = "AM"
        return f"{h12:02d}:{m:02d}:{s:02d} {ampm} {emoji}"

def run_linear_meridian_clock():
    try:
        while True:
            current_unix_time = int(time.time())
            info = get_game_time(current_unix_time)
            time_24 = format_game_time(info, use_24h=True)
            time_12 = format_game_time(info, use_24h=False)

            # Wipe the command window via native OS system call
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Render the UI text block
            output_buffer = (
                f"--- Meridian 59 Linear Time Engine ---\n"
                f"Your Local PC Time: {datetime.now().strftime('%H:%M:%S')}\n"
                f"Raw Global Epoch:   {current_unix_time}\n"
                f"Game Time (24h):    {time_24}\n"
                f"Game Time (12h):    {time_12}\n"
                f"World State:        {info['state_desc']}\n"
                f"Next Clock Tick:    In {info['countdown']}\n"
                f"---------------------------------------\n"
                f"Press Ctrl+C to exit."
            )
            
            sys.stdout.write(output_buffer)
            sys.stdout.flush()

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nClock engine paused. Safe travels in the main loop!")

if __name__ == "__main__":
    run_linear_meridian_clock()
