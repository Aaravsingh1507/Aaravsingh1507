#!/usr/bin/env python3
"""
Generate GitHub Statistics Dashboard SVG using live real data.
Replicates the sleek modern GitHub dark dashboard design with 100% pixel precision.
"""

import os
import sys
import json
import subprocess
import urllib.request
import re
from datetime import datetime, date

USERNAME = "Aaravsingh1507"

def get_token():
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        if token:
            return token
    except Exception:
        pass
    return None

def fetch_graphql_data(token):
    query = """
    query($login: String!) {
      user(login: $login) {
        name
        login
        createdAt
        contributionsCollection {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
        repositoriesContributedTo(first: 1) {
          totalCount
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes {
            name
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Stats-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request("https://api.github.com/graphql", data=payload, headers=headers)
    res = urllib.request.urlopen(req)
    data = json.loads(res.read().decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]

def fetch_streak_stats():
    """Fetch streak numbers and ranges from demolab streak API, with fallback."""
    try:
        url = f"https://streak-stats.demolab.com/?user={USERNAME}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        res = urllib.request.urlopen(req, timeout=15)
        content = res.read().decode("utf-8")
        
        # Demolab SVG text elements in order:
        # [0] total contributions (e.g. '89')
        # [1] 'Total Contributions'
        # [2] total range (e.g. 'Aug 11, 2025 - Present')
        # [3] 'Current Streak'
        # [4] current range (e.g. 'Oct 27 - Oct 28')
        # [5] current streak (e.g. '2')
        # [6] longest streak (e.g. '5')
        # [7] 'Longest Streak'
        # [8] longest range (e.g. 'Oct 3 - Oct 7')
        vals = re.findall(r'<text[^>]*>\s*([^<\s][^<]*?)\s*</text>', content)
        if len(vals) >= 9:
            return {
                "total_contributions": vals[0],
                "total_range": vals[2],
                "current_streak": vals[5],
                "current_range": vals[4],
                "longest_streak": vals[6],
                "longest_range": vals[8]
            }
    except Exception as e:
        print(f"Demolab streak fetch notice: {e}. Falling back to calendar computation.", file=sys.stderr)
    return None

def compute_streak_from_calendar(user_data):
    """Fallback streak calculation if demolab is unreachable."""
    weeks = user_data["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = []
    for w in weeks:
        for d in w["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort(key=lambda x: x[0])
    
    # Calculate longest streak
    longest = 0
    longest_start = None
    longest_end = None
    temp = 0
    temp_start = None
    
    for d_str, count in days:
        if count > 0:
            if temp == 0:
                temp_start = d_str
            temp += 1
            if temp > longest:
                longest = temp
                longest_start = temp_start
                longest_end = d_str
        else:
            temp = 0
            temp_start = None
            
    # Calculate current streak
    curr = 0
    curr_start = None
    curr_end = None
    for d_str, count in reversed(days):
        if count > 0:
            if curr == 0:
                curr_end = d_str
            curr += 1
            curr_start = d_str
        else:
            if curr > 0:
                break
                
    def fmt_range(s, e):
        if not s or not e:
            return ""
        d1 = datetime.strptime(s, "%Y-%m-%d")
        d2 = datetime.strptime(e, "%Y-%m-%d")
        return f"{d1.strftime('%b %d').replace(' 0', ' ')} - {d2.strftime('%b %d').replace(' 0', ' ')}"

    first_contrib_date = next((d[0] for d in days if d[1] > 0), user_data.get("createdAt", "")[:10])
    if first_contrib_date:
        fc = datetime.strptime(first_contrib_date[:10], "%Y-%m-%d")
        total_range = f"{fc.strftime('%b %d, %Y').replace(' 0', ' ')} - Present"
    else:
        total_range = "Present"

    return {
        "total_contributions": str(user_data["contributionsCollection"]["contributionCalendar"]["totalContributions"]),
        "total_range": total_range,
        "current_streak": str(curr),
        "current_range": fmt_range(curr_start, curr_end),
        "longest_streak": str(longest),
        "longest_range": fmt_range(longest_start, longest_end)
    }

def generate_svg(user, streak_info):
    name = user.get("name") or "Aarav Singh"
    coll = user["contributionsCollection"]
    commits = coll["totalCommitContributions"]
    prs = coll["totalPullRequestContributions"]
    issues = coll["totalIssueContributions"]
    contributed_to = user["repositoriesContributedTo"]["totalCount"]
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    
    # Calculate languages
    lang_sizes = {}
    lang_colors = {}
    for r in user["repositories"]["nodes"]:
        for edge in r["languages"]["edges"]:
            lname = edge["node"]["name"]
            lcolor = edge["node"]["color"]
            lsize = edge["size"]
            lang_sizes[lname] = lang_sizes.get(lname, 0) + lsize
            if lcolor:
                lang_colors[lname] = lcolor

    total_lang_size = sum(lang_sizes.values())
    sorted_langs = sorted(lang_sizes.items(), key=lambda x: x[1], reverse=True)[:6]
    
    # Language progress bar segments (total bar width = 928)
    bar_width = 928
    bar_segments = []
    curr_x = 0
    for lname, lsize in sorted_langs:
        pct = (lsize / total_lang_size) * 100
        seg_w = (lsize / total_lang_size) * bar_width
        color = lang_colors.get(lname, "#8b949e")
        bar_segments.append({
            "name": lname,
            "pct": f"{pct:.2f}%",
            "pct_num": pct,
            "color": color,
            "x": curr_x,
            "width": seg_w
        })
        curr_x += seg_w

    total_contribs = streak_info["total_contributions"]
    total_range = streak_info["total_range"]
    curr_streak = streak_info["current_streak"]
    curr_range = streak_info["current_range"]
    long_streak = streak_info["longest_streak"]
    long_range = streak_info["longest_range"]

    # Build SVG XML
    svg = f"""<svg width="1024" height="515" viewBox="0 0 1024 515" fill="none" xmlns="http://www.w3.org/2000/svg" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
  <defs>
    <!-- Bar clip for progress bar -->
    <clipPath id="lang-bar-clip">
      <rect x="48" y="385" width="928" height="11" rx="5.5" />
    </clipPath>
    <!-- Mask for fire ring -->
    <mask id="fire-ring-mask">
      <rect width="1024" height="515" fill="white" />
      <ellipse cx="720" cy="138" rx="14" ry="15" fill="black" />
    </mask>
  </defs>

  <!-- ================= TOP BADGE: 📊 GitHub Statistics ================= -->
  <g id="badge-header">
    <rect x="23" y="20" width="350" height="68" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
    
    <!-- Chart Icon Badge -->
    <g transform="translate(44, 32)">
      <rect width="40" height="44" rx="8" fill="#ffffff" />
      <!-- Green bar -->
      <rect x="7" y="18" width="6" height="20" rx="2" fill="#3fb950" />
      <!-- Magenta bar -->
      <rect x="17" y="10" width="6" height="28" rx="2" fill="#d946ef" />
      <!-- Blue bar -->
      <rect x="27" y="5" width="6" height="33" rx="2" fill="#388bfd" />
    </g>
    
    <!-- Title -->
    <text x="98" y="64" font-size="28" font-weight="700" fill="#f0f6fc">GitHub Statistics</text>
  </g>

  <!-- ================= CARD 1: Aarav Singh's GitHub Stats ================= -->
  <g id="card-github-stats">
    <rect x="23" y="106" width="387" height="221" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
    <text x="44" y="142" font-size="18" font-weight="700" fill="#f0f6fc">{name}&apos;s GitHub Stats</text>

    <!-- Row 1: Stars -->
    <g transform="translate(45, 161)">
      <!-- Star icon (outline) -->
      <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z" fill="none" stroke="#1f6feb" stroke-width="1.4" />
      <text x="26" y="13" font-size="13" font-weight="500" fill="#c9d1d9">Total Stars Earned:</text>
      <text x="340" y="13" text-anchor="end" font-size="14" font-weight="700" fill="#f0f6fc">{stars}</text>
    </g>

    <!-- Row 2: Commits -->
    <g transform="translate(45, 192)">
      <!-- History / Clock icon -->
      <path d="M1.643 3.143L.427 1.927A.25.25 0 000 2.104V5.75c0 .138.112.25.25.25h3.646a.25.25 0 00.177-.427L2.715 4.215a6.5 6.5 0 11-1.18 4.458.75.75 0 10-1.493.154 8.001 8.001 0 101.6-5.684zM7.75 4a.75.75 0 01.75.75v2.99l2.03 1.172a.75.75 0 11-.75 1.3l-2.404-1.388A.75.75 0 017 8.172V4.75A.75.75 0 017.75 4z" fill="#1f6feb" />
      <text x="26" y="13" font-size="13" font-weight="500" fill="#c9d1d9">Total Commits (last year):</text>
      <text x="340" y="13" text-anchor="end" font-size="14" font-weight="700" fill="#f0f6fc">{commits}</text>
    </g>

    <!-- Row 3: PRs -->
    <g transform="translate(45, 223)">
      <!-- Pull request icon -->
      <path d="M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.128a2.251 2.251 0 11-1.5 0V5.372a2.25 2.25 0 00-1.5-2.122V1.5a.75.75 0 01.75-.75h1A2.5 2.5 0 0113.5 3.25v6.878a2.25 2.25 0 11-1.5 0V5a.5.5 0 00-.5-.5z" fill="#1f6feb" />
      <text x="26" y="13" font-size="13" font-weight="500" fill="#c9d1d9">Total PRs:</text>
      <text x="340" y="13" text-anchor="end" font-size="14" font-weight="700" fill="#f0f6fc">{prs}</text>
    </g>

    <!-- Row 4: Issues -->
    <g transform="translate(45, 254)">
      <!-- Issue icon -->
      <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm9 3a1 1 0 11-2 0 1 1 0 012 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z" fill="#1f6feb" />
      <text x="26" y="13" font-size="13" font-weight="500" fill="#c9d1d9">Total Issues:</text>
      <text x="340" y="13" text-anchor="end" font-size="14" font-weight="700" fill="#f0f6fc">{issues}</text>
    </g>

    <!-- Row 5: Contributed to -->
    <g transform="translate(45, 285)">
      <!-- Contributed / Repo icon -->
      <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" fill="#1f6feb" />
      <text x="26" y="13" font-size="13" font-weight="500" fill="#c9d1d9">Contributed to (last year):</text>
      <text x="340" y="13" text-anchor="end" font-size="14" font-weight="700" fill="#f0f6fc">{contributed_to}</text>
    </g>
  </g>

  <!-- ================= CARD 2: Total Contributions ================= -->
  <g id="card-total-contribs">
    <rect x="422" y="106" width="195" height="221" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
    
    <!-- Circle Track & Blue Arc -->
    <circle cx="520" cy="178" r="48" fill="none" stroke="#162032" stroke-width="6"/>
    <!-- Highlight arc on upper side -->
    <path d="M 486 144 A 48 48 0 0 1 542 138" fill="none" stroke="#1f6feb" stroke-width="6" stroke-linecap="round"/>
    
    <!-- GitHub Octocat Silhouette in Center -->
    <g transform="translate(506, 163)">
      <path fill-rule="evenodd" clip-rule="evenodd" d="M14 0C6.27 0 0 6.27 0 14c0 6.19 4.01 11.43 9.57 13.28.7.13.96-.3.96-.67v-2.36c-3.89.85-4.71-1.87-4.71-1.87-.64-1.61-1.56-2.04-1.56-2.04-1.27-.87.1-.85.1-.85 1.4.1 2.14 1.44 2.14 1.44 1.25 2.13 3.27 1.52 4.06 1.16.13-.9.49-1.52.89-1.87-3.1-.35-6.36-1.55-6.36-6.91 0-1.53.54-2.77 1.44-3.75-.14-.35-.62-1.77.14-3.69 0 0 1.17-.38 3.85 1.44A13.4 13.4 0 0114 6c1.19.01 2.39.16 3.51.47 2.68-1.81 3.85-1.44 3.85-1.44.76 1.92.28 3.34.14 3.69.9.97 1.44 2.22 1.44 3.75 0 5.37-3.27 6.55-6.38 6.9.5.43.95 1.28.95 2.59v3.84c0 .38.25.81.97.67C23.99 25.42 28 20.19 28 14c0-7.73-6.27-14-14-14z" fill="#ffffff"/>
    </g>

    <!-- Big Number -->
    <text x="520" y="258" text-anchor="middle" font-size="28" font-weight="700" fill="#ffffff">{total_contribs}</text>
    <!-- Label -->
    <text x="520" y="280" text-anchor="middle" font-size="13" font-weight="500" fill="#c9d1d9">Total Contributions</text>
    <!-- Range -->
    <text x="520" y="302" text-anchor="middle" font-size="12" font-weight="500" fill="#3fb950">{total_range}</text>
  </g>

  <!-- ================= CARD 3: Current Streak ================= -->
  <g id="card-current-streak">
    <rect x="628" y="106" width="183" height="221" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
    
    <!-- Masked Ring with Flame Icon at Top -->
    <g mask="url(#fire-ring-mask)">
      <circle cx="720" cy="178" r="46" fill="none" stroke="#1f6feb" stroke-width="6"/>
    </g>
    
    <!-- Flame Icon sitting at top of circle -->
    <g transform="translate(720, 128)">
      <path d="M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 C 4.51 16.85 2.36 19 -0.29 19 Z" fill="#388bfd"/>
    </g>

    <!-- Number in Ring -->
    <text x="720" y="188" text-anchor="middle" font-size="28" font-weight="700" fill="#ffffff">{curr_streak}</text>
    
    <!-- Label -->
    <text x="720" y="258" text-anchor="middle" font-size="14" font-weight="700" fill="#388bfd">Current Streak</text>
    <!-- Range -->
    <text x="720" y="280" text-anchor="middle" font-size="12" font-weight="500" fill="#3fb950">{curr_range}</text>
  </g>

  <!-- ================= CARD 4: Longest Streak ================= -->
  <g id="card-longest-streak">
    <rect x="823" y="106" width="179" height="221" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
    
    <!-- Dark Circle Ring -->
    <circle cx="912" cy="178" r="46" fill="none" stroke="#16273f" stroke-width="6"/>
    
    <!-- Trophy Icon sitting at top of circle -->
    <g transform="translate(900, 126)">
      <!-- Trophy SVG path -->
      <path d="M19 3H16V2C16 1.45 15.55 1 15 1H9C8.45 1 8 1.45 8 2V3H5C3.9 3 3 3.9 3 5V9C3 11.76 5.24 14 8 14H8.2C8.75 15.42 9.87 16.57 11.3 16.89V19H9C8.45 19 8 19.45 8 20V21H16V20C16 19.45 15.55 19 15 19H12.7V16.89C14.13 16.57 15.25 15.42 15.8 14H16C18.76 14 21 11.76 21 9V5C21 3.9 20.1 3 19 3ZM5 9V5H8V9.8C6.27 9.4 5 7.85 5 9ZM19 9C19 7.85 17.73 9.4 16 9.8V5H19V9Z" fill="#1f6feb"/>
    </g>

    <!-- Number in Ring -->
    <text x="912" y="188" text-anchor="middle" font-size="28" font-weight="700" fill="#ffffff">{long_streak}</text>
    
    <!-- Label -->
    <text x="912" y="258" text-anchor="middle" font-size="14" font-weight="700" fill="#f0f6fc">Longest Streak</text>
    <!-- Range -->
    <text x="912" y="280" text-anchor="middle" font-size="12" font-weight="500" fill="#3fb950">{long_range}</text>
  </g>

  <!-- ================= CARD 5: Most Used Languages ================= -->
  <g id="card-languages">
    <rect x="23" y="342" width="979" height="152" rx="14" fill="#0d1117" stroke="#30363d" stroke-width="1.5"/>
    <text x="48" y="373" font-size="18" font-weight="700" fill="#f0f6fc">Most Used Languages</text>

    <!-- Full-width Multi-Color Progress Bar -->
    <g clip-path="url(#lang-bar-clip)">
"""
    # Append progress bar segments
    for seg in bar_segments:
        svg += f'      <rect x="{48 + seg["x"]:.1f}" y="385" width="{seg["width"]:.1f}" height="11" fill="{seg["color"]}" />\n'

    svg += """    </g>

    <!-- Center vertical separator line -->
    <line x1="495" y1="408" x2="495" y2="480" stroke="#21262d" stroke-width="1" />

    <!-- Languages Breakdown (2 columns, 3 rows each) -->
"""

    # Left column (up to 3 items)
    y_coords = [426, 452, 478]
    left_items = bar_segments[:3]
    for i, item in enumerate(left_items):
        y = y_coords[i]
        svg += f"""    <g>
      <circle cx="136" cy="{y - 5}" r="5" fill="{item['color']}" />
      <text x="156" y="{y}" font-size="13" font-weight="500" fill="#c9d1d9">{item['name']}</text>
      <text x="420" y="{y}" text-anchor="end" font-size="13" font-weight="600" fill="#f0f6fc">{item['pct']}</text>
    </g>
"""

    # Right column (up to 3 items)
    right_items = bar_segments[3:6]
    for i, item in enumerate(right_items):
        y = y_coords[i]
        svg += f"""    <g>
      <circle cx="602" cy="{y - 5}" r="5" fill="{item['color']}" />
      <text x="622" y="{y}" font-size="13" font-weight="500" fill="#c9d1d9">{item['name']}</text>
      <text x="890" y="{y}" text-anchor="end" font-size="13" font-weight="600" fill="#f0f6fc">{item['pct']}</text>
    </g>
"""

    svg += """  </g>
</svg>
"""
    return svg

def main():
    token = get_token()
    print("Fetching live GitHub statistics for:", USERNAME)
    user_data = fetch_graphql_data(token)
    
    streak_info = fetch_streak_stats()
    if not streak_info:
        print("Using computed streak from GraphQL contribution calendar...")
        streak_info = compute_streak_from_calendar(user_data)
        
    print(f"Stats: Commits={user_data['contributionsCollection']['totalCommitContributions']}, TotalContribs={streak_info['total_contributions']}, CurrentStreak={streak_info['current_streak']}, LongestStreak={streak_info['longest_streak']}")
    
    svg_content = generate_svg(user_data, streak_info)
    
    output_dir = os.path.join(os.path.dirname(__file__), "..", "profile-stats")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "github-stats.svg")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
        
    print(f"Successfully generated dashboard SVG at: {output_path}")

if __name__ == "__main__":
    main()
