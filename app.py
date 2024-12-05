import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import json
import altair as alt
from streamlit.components.v1 import html
import re

# =======================
# 1. Load and Prepare Data
# =======================

@st.cache_data
def load_election_data():
    with open('structured_election_data.json', 'r') as f:
        structured_data = json.load(f)
    records = []
    parties = set()
    states = set()
    districts = set()

    def normalize_party_name(party_name):
        if party_name is None:
            return None
        party_name = party_name.strip().lower()
        if 'green' in party_name:
            return 'Green'
        elif party_name in ['democrat', 'democratic']:
            return 'D'
        elif party_name in ['republican']:
            return 'R'
        else:
            return party_name.title()

    for state_entry in structured_data:
        state = state_entry['state']
        if state is not None:
            states.add(state)
        for district_entry in state_entry['districts']:
            district = district_entry['district']
            if district is not None:
                districts.add(district)
            for candidate in district_entry['candidates']:
                try:
                    percentage = float(candidate['percentage']) if candidate['percentage'] else None
                except (ValueError, TypeError):
                    percentage = None  # Handle as NaN

                normalized_party = normalize_party_name(candidate['party'])
                if normalized_party is not None:
                    parties.add(normalized_party)

                record = {
                    'state': state,
                    'district': district,
                    'candidate': candidate['candidate'],
                    'party': normalized_party,
                    'votes': int(candidate['votes']),
                    'percentage': percentage
                }
                records.append(record)
    df = pd.DataFrame(records)

    # Filter out None values before sorting
    parties = [p for p in parties if p is not None]
    parties = sorted(parties)
    states = [s for s in states if s is not None]
    states = sorted(states)
    districts = [d for d in districts if d is not None]
    districts = sorted(districts)

    return df, parties, states, districts

@st.cache_data
def load_geo_data():
    state_code_to_name = {
        "01": "Alabama",
        "02": "Alaska",
        "04": "Arizona",
        "05": "Arkansas",
        "06": "California",
        "08": "Colorado",
        "09": "Connecticut",
        "10": "Delaware",
        "11": "District of Columbia",
        "12": "Florida",
        "13": "Georgia",
        "15": "Hawaii",
        "16": "Idaho",
        "17": "Illinois",
        "18": "Indiana",
        "19": "Iowa",
        "20": "Kansas",
        "21": "Kentucky",
        "22": "Louisiana",
        "23": "Maine",
        "24": "Maryland",
        "25": "Massachusetts",
        "26": "Michigan",
        "27": "Minnesota",
        "28": "Mississippi",
        "29": "Missouri",
        "30": "Montana",
        "31": "Nebraska",
        "32": "Nevada",
        "33": "New Hampshire",
        "34": "New Jersey",
        "35": "New Mexico",
        "36": "New York",
        "37": "North Carolina",
        "38": "North Dakota",
        "39": "Ohio",
        "40": "Oklahoma",
        "41": "Oregon",
        "42": "Pennsylvania",
        "44": "Rhode Island",
        "45": "South Carolina",
        "46": "South Dakota",
        "47": "Tennessee",
        "48": "Texas",
        "49": "Utah",
        "50": "Vermont",
        "51": "Virginia",
        "53": "Washington",
        "54": "West Virginia",
        "55": "Wisconsin",
        "56": "Wyoming",
        "60": "American Samoa",
        "66": "Guam",
        "69": "Northern Mariana Islands",
        "72": "Puerto Rico",
        "78": "Virgin Islands"
    }

    geo_df = gpd.read_file('./simplemaps_congress_basicv1.9/congress.shp')
    geo_df['state_code'] = geo_df['fips'].str[:2]  # Extract the first two characters for state code
    geo_df['state_name'] = geo_df['state_code'].map(state_code_to_name)  # Map to state name

    def process_code(code):
        number = ''.join(filter(str.isdigit, code))
        return str(int(number)) if number else '0'

    geo_df['district'] = geo_df['id'].apply(process_code)

    return geo_df

# =======================
# 2. Helper Functions
# =======================

def get_winner_and_margin(group):
    sorted_group = group.sort_values('votes', ascending=False)
    winner = sorted_group.iloc[0]
    if len(sorted_group) > 1:
        runner_up = sorted_group.iloc[1]
        margin = winner['votes'] - runner_up['votes']
    else:
        margin = winner['votes']
    return pd.Series({
        'winner_name': winner['candidate'],
        'winner_party': winner['party'],
        'winner_votes': winner['votes'],
        'margin_of_victory': margin
    })

def calculate_house_score(winners_df):
    # Calculates the number of seats won by each party
    party_counts = winners_df['winner_party'].value_counts().reset_index()
    party_counts.columns = ['Party', 'Seats Won']
    return party_counts

def plot_house_score(house_score):
    # Calculate percentage
    total_seats = house_score['Seats Won'].sum()
    house_score['Percentage'] = (house_score['Seats Won'] / total_seats) * 100

    # Sort house_score to have consistent order (e.g., D, R, Green)
    house_score = house_score.sort_values(['Party'], ascending=True)

    # Add a dummy category for Y-axis to create a single bar
    house_score['Category'] = 'Total'

    # Calculate cumulative percentage for label positioning
    house_score['Cumulative'] = house_score['Percentage'].cumsum()

    # Create labels with seat counts
    house_score['Party_Label'] = house_score['Party'] + ' (' + house_score['Seats Won'].astype(str) + ')'

    # Create a horizontal stacked bar chart
    chart = alt.Chart(house_score).mark_bar(size=30).encode(
        x=alt.X('Percentage:Q', stack='zero', title=None, axis=None),
        y=alt.Y('Category:N', sort=None, title=None, axis=None),
        color=alt.Color('Party:N', scale=alt.Scale(domain=['D', 'R', 'Green'], range=['#ADD8E6', '#FFC0CB', '#98FB98']), legend=None),
        tooltip=['Party:N', 'Seats Won:Q', alt.Tooltip('Percentage:Q', format='.1f')]
    ).properties(
        height=100,  # Increased height to accommodate labels below
        width=600,
    )

    # Prepare labels for the ends with seat counts
    # Get the first and last parties for labeling
    first_party = house_score.iloc[0]
    last_party = house_score.iloc[-1]

    # Create a dataframe for labels
    label_df = pd.DataFrame({
        'Party_Label': [house_score['Party_Label'].iloc[0], house_score['Party_Label'].iloc[-1]],
        'Position': [0, house_score['Cumulative'].iloc[-1]]
    })

    # Add labels at the start and end below the bar
    label_start = alt.Chart(label_df.iloc[[0]]).mark_text(
        align='left',
        baseline='middle',
        dx=5,   # Shift text slightly to the right
        dy=25   # Increased shift below the bar to prevent overlap
    ).encode(
        x=alt.X('Position:Q'),
        y=alt.Y('Category:N', axis=None),
        text='Party_Label:N'
    )

    label_end = alt.Chart(label_df.iloc[[1]]).mark_text(
        align='right',
        baseline='middle',
        dx=-5,  # Shift text slightly to the left
        dy=25   # Increased shift below the bar to prevent overlap
    ).encode(
        x=alt.X('Position:Q'),
        y=alt.Y('Category:N', axis=None),
        text='Party_Label:N'
    )

    # Combine chart and labels
    final_chart = (chart + label_start + label_end).configure_view(
        strokeWidth=0  # Remove border around the chart
    ).configure(background='#FFFFFF')

    return final_chart

def prepare_data(all_results):
    # Calculate total votes and vote share
    all_results['total_votes'] = all_results.groupby(['state', 'district'])['votes'].transform('sum')
    all_results['vote_share'] = all_results['votes'] / all_results['total_votes']

    # Identify winners and calculate margin of victory
    winners = all_results.groupby(['state', 'district']).apply(get_winner_and_margin).reset_index()

    # Merge winner information back into all_results with suffixes to handle duplicates
    all_results = all_results.merge(winners, on=['state', 'district'], how='left', suffixes=('', '_winner'))

    # If 'winner_name_winner' exists, replace 'winner_name' with it and drop the duplicate
    if 'winner_name_winner' in all_results.columns:
        all_results['winner_name'] = all_results['winner_name_winner']
        all_results['winner_party'] = all_results['winner_party_winner']
        all_results['winner_votes'] = all_results['winner_votes_winner']
        all_results['margin_of_victory'] = all_results['margin_of_victory_winner']
        # Drop the duplicate columns
        all_results.drop(columns=['winner_name_winner', 'winner_party_winner', 'winner_votes_winner', 'margin_of_victory_winner'], inplace=True)

    return all_results, winners

def get_smallest_margins(data, n=5):
    margins = data[['state', 'district', 'margin_of_victory']].drop_duplicates()
    smallest_margins = margins.nsmallest(n, 'margin_of_victory')
    return smallest_margins

# =======================
# 3. Vote Redistribution Function
# =======================

def redistribute_votes(data, from_parties, to_party, state=None, district=None):
    data = data.copy()

    # Define filters based on state and district if provided
    filters = pd.Series([True] * len(data))
    if state:
        filters &= data['state'] == state
    if district:
        filters &= data['district'] == district

    # Identify 'from_parties' candidates within filters
    from_candidates = data[data['party'].isin(from_parties) & filters]

    if from_candidates.empty:
        st.warning("No candidates found for the selected 'from_parties' within the specified filters.")
        return data

    # Subtract votes from 'from_parties' candidates
    data.loc[from_candidates.index, 'votes'] = 0

    # Group by state and district to redistribute votes
    grouped = from_candidates.groupby(['state', 'district'])

    for (grp_state, grp_district), group in grouped:
        # Sum votes to be transferred in this state and district
        votes_to_transfer = group['votes'].sum()

        # Find 'to_party' candidates in this state and district
        to_party_candidates = data[(data['state'] == grp_state) &
                                   (data['district'] == grp_district) &
                                   (data['party'] == to_party)]

        if not to_party_candidates.empty:
            # Identify the top-voted 'to_party' candidate
            top_to_party_candidate = to_party_candidates.sort_values('votes', ascending=False).iloc[0]
            # Add votes to this candidate
            data.loc[top_to_party_candidate.name, 'votes'] += votes_to_transfer
        else:
            # If no 'to_party' candidate exists, create one
            new_candidate = {
                'state': grp_state,
                'district': grp_district,
                'candidate': f'New {to_party} Candidate',
                'party': to_party,
                'votes': votes_to_transfer,
                'percentage': 0,
                'total_votes': 0,
                'vote_share': 0,
                'winner_name': '',
                'winner_party': '',
                'winner_votes': 0,
                'margin_of_victory': 0
            }
            # Append the new candidate
            data = pd.concat([data, pd.DataFrame([new_candidate])], ignore_index=True)

    # Recalculate totals and percentages
    data['total_votes'] = data.groupby(['state', 'district'])['votes'].transform('sum')
    data['vote_share'] = data['votes'] / data['total_votes'] * 100
    data['percentage'] = data['vote_share']

    # Re-identify winners
    winners = data.groupby(['state', 'district']).apply(get_winner_and_margin).reset_index()
    data = data.drop(columns=['winner_name', 'winner_party', 'winner_votes', 'margin_of_victory'])
    data = data.merge(winners, on=['state', 'district'], how='left', suffixes=('', '_winner'))

    # Handle duplicate columns after merge
    if 'winner_name_winner' in data.columns:
        data['winner_name'] = data['winner_name_winner']
        data['winner_party'] = data['winner_party_winner']
        data['winner_votes'] = data['winner_votes_winner']
        data['margin_of_victory'] = data['margin_of_victory_winner']
        data.drop(columns=['winner_name_winner', 'winner_party_winner', 'winner_votes_winner', 'margin_of_victory_winner'], inplace=True)

    return data

# =======================
# 4. Map Visualization Function
# =======================

def create_map(geo_df, map_df, opacity_field=None):
    """
    Create a Folium map with districts colored based on the winning party and opacity based on vote share.
    The map has a pure white background with no base tiles, displaying only the plotted shapes.
    The map view is adjusted to fit the bounds of the district shapes.
    """
    # Define pastel colors
    party_color_map = {
        'D': '#ADD8E6',     # Light Blue for Democrats
        'R': '#FFC0CB',     # Light Pink for Republicans
        'Green': '#98FB98', # Pale Green for Green Party
        # Add other parties if necessary
    }

    def party_color(party):
        """
        Retrieve color based on party.
        """
        return party_color_map.get(party, '#D3D3D3')  # Light Gray for others

    # Create the base Folium map without background tiles
    m = folium.Map(location=[37.8, -96.9], zoom_start=4, tiles=None, control_scale=False, zoom_control=False)

    # Enhanced CSS to ensure white background and remove any residual styles
    m.get_root().html.add_child(folium.Element("""
        <style>
        /* Ensure the entire map container has a white background */
        .leaflet-container {
            background: #FFFFFF !important;
        }
        /* Remove any background from Leaflet panes */
        .leaflet-pane {
            background: #FFFFFF !important;
        }
        /* Ensure tooltips have a white background */
        .leaflet-tooltip {
            background-color: rgba(255, 255, 255, 0.8) !important;
            color: #000000 !important;
            border: 1px solid #CCCCCC !important;
        }
        /* Remove any default background images or patterns */
        .leaflet-tile-pane, .leaflet-marker-pane, .leaflet-overlay-pane, .leaflet-shadow-pane, .leaflet-popup-pane {
            background: transparent !important;
        }
        </style>
        """))

    # Remove default controls
    m.options['zoomControl'] = False
    m.options['doubleClickZoom'] = False
    m.options['scrollWheelZoom'] = False
    m.options['touchZoom'] = False

    # Define a function for style
    def style_function(feature):
        fill_color = party_color(feature['properties'].get('winner_party'))
        fill_opacity = 1.0  # default

        if opacity_field and opacity_field in feature['properties']:
            # Assuming 'fill_opacity' is already a float between 0.5 and 1.0
            fill_opacity = feature['properties'].get(opacity_field, 0.5)
        return {
            'fillColor': fill_color,
            'color': 'black',
            'weight': 0.5,
            'fillOpacity': fill_opacity,
        }

    # Add GeoJSON layer
    folium.GeoJson(
        map_df.__geo_interface__,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=['tooltip'],
            aliases=[''],
            labels=False,
            sticky=True
        )
    ).add_to(m)

    # Fit map to bounds
    bounds = map_df.total_bounds  # [minx, miny, maxx, maxy]
    sw = [bounds[1], bounds[0]]  # [miny, minx]
    ne = [bounds[3], bounds[2]]  # [maxy, maxx]
    m.fit_bounds([sw, ne])

    # Render the map as HTML
    map_html = m.get_root().render()

    return map_html

# =======================
# 5. Tooltip Creation Function
# =======================

def create_tooltip(row):
    """
    Create HTML tooltip for each district.
    """
    tooltip = f"State: {row.get('state_name', 'Unknown')}, District: {row.get('district', 'Unknown')}<br>"
    tooltip += f"Winner: {row.get('winner_name', 'Unknown')} ({row.get('winner_party', 'Unknown')}), Votes: {row.get('winner_votes', 0)}<br>"
    tooltip += f"Margin of Victory: {row.get('margin_of_victory', 'Unknown')}<br>"
    if isinstance(row.get('other_candidates'), list) and row['other_candidates']:
        for candidate in row['other_candidates']:
            tooltip += f"{candidate.get('candidate', 'Unknown')} ({candidate.get('party', 'Unknown')}), Votes: {candidate.get('votes', 0)}<br>"
    return tooltip

# =======================
# 6. Custom CSS Styling
# =======================

def set_custom_style():
    st.markdown(
        """
        <style>
        /* Import Google Font: Roboto */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');

        /* Apply Roboto font globally */
        body, .css-1d391kg, .css-1y4p8pa {
            font-family: 'Roboto', sans-serif;
        }

        /* Set headers and subheaders to black */
        h1, h2, h3, h4, h5, h6 {
            color: #000000;
        }

        /* Optional: Customize button styles to match the minimalist theme */
        .css-1emrehy.edgvbvh3 {
            background-color: #f0f0f0;
            color: #000000;
            border: none;
            border-radius: 5px;
        }

        /* Ensure the app background remains white */
        .stApp {
            background-color: #FFFFFF;
        }

        /* Style for Tabs */
        /* Target unselected tab labels */
        .stTabs [role="tab"] {
            color: #000000;
            font-weight: 400;
        }

        /* Style for selected tab label */
        .stTabs [role="tab"][aria-selected="true"] {
            color: #000000;
            font-weight: 700;
        }

        </style>
        """,
        unsafe_allow_html=True
    )

# =======================
# 7. Streamlit Application
# =======================

def main():
    set_custom_style()

    st.title("US House Election Results Analysis")

    # =======================
    # Sidebar: Analysis Type Selection with Vertical Tabs
    # =======================
    analysis_type = st.sidebar.radio("", ["View Original Results", "Vote Redistribution", "Analytical Questions"])

    # Load data
    all_results, parties, states, districts = load_election_data()
    geo_df = load_geo_data()
    all_results, winners = prepare_data(all_results)

    if analysis_type == "View Original Results":
        st.header("Original Election Results")

        # Calculate and display the house score
        house_score = calculate_house_score(winners)
        chart = plot_house_score(house_score)
        st.altair_chart(chart, use_container_width=True)

        # Prepare map data
        geo_df['state_name'] = geo_df['state_name'].str.title()

        # Winning Party Map DataFrame
        winning_map_df = pd.merge(
            geo_df,
            winners[['state', 'district', 'winner_name', 'winner_party', 'winner_votes', 'margin_of_victory']],
            left_on=['state_name', 'district'],
            right_on=['state', 'district'],
            how='inner'
        )

        # Collect other candidates
        other_candidates = (
            all_results[all_results['candidate'] != all_results['winner_name']]
            .groupby(['state', 'district'])
            .apply(lambda group: group[['candidate', 'party', 'votes']].to_dict(orient='records'))
            .reset_index(name='other_candidates')
        )

        # Merge other_candidates into winning_map_df
        winning_map_df = pd.merge(
            winning_map_df,
            other_candidates,
            on=['state', 'district'],
            how='left'
        )

        # Convert to GeoDataFrame
        winning_map_df = gpd.GeoDataFrame(winning_map_df, geometry='geometry')

        # Compute vote share for the winning party
        def compute_vote_share(row):
            if isinstance(row['other_candidates'], list):
                other_votes = sum([c['votes'] for c in row['other_candidates']])
            else:
                other_votes = 0
            total_votes = row['winner_votes'] + other_votes
            return (row['winner_votes'] / total_votes) * 100 if total_votes > 0 else 0

        winning_map_df['vote_share'] = winning_map_df.apply(compute_vote_share, axis=1)

        # Define opacity based on vote_share
        # Opacity ranges from 0.5 (50%) to 1.0 (100%)
        def compute_opacity(vote_share):
            min_opacity = 0.5
            max_opacity = 1.0
            # Assuming vote_share ranges from 50% to 100%
            if vote_share < 50:
                return min_opacity
            elif vote_share > 100:
                return max_opacity
            else:
                return min_opacity + (vote_share - 50) / 50 * (max_opacity - min_opacity)

        winning_map_df['fill_opacity'] = winning_map_df['vote_share'].apply(compute_opacity)

        # Save the original map data to session state
        st.session_state['original_map_df'] = winning_map_df

        # Create tabs for different map views
        map_tabs = st.tabs(["Winning Party Map", "Weighted Opacity Map"])

        with map_tabs[0]:
            st.subheader("Winning Party Map")
            if winning_map_df.empty:
                st.error("The map data is empty. Please check your inputs and data processing.")
            else:
                winning_map_df['tooltip'] = winning_map_df.apply(create_tooltip, axis=1)
                winning_map_html = create_map(geo_df, winning_map_df)
                # Render the map HTML
                html(winning_map_html, height=500)

        with map_tabs[1]:
            st.subheader("Weighted Opacity Map")
            if winning_map_df.empty:
                st.error("The map data is empty. Please check your inputs and data processing.")
            else:
                # Create the map with opacity based on vote_share
                weighted_map_html = create_map(geo_df, winning_map_df, opacity_field='fill_opacity')
                # Render the weighted opacity map HTML
                html(weighted_map_html, height=500)

    elif analysis_type == "Vote Redistribution":
        st.header("Simulate Vote Redistribution")

        # =======================
        # Vote Redistribution Options
        # =======================
        st.subheader("Redistribution Parameters")

        # Dropdown for From Parties (Multiple Selection)
        from_parties = st.multiselect("From Parties", options=parties, default=["Green"])

        # Dropdown for To Party (Single Selection)
        to_party = st.selectbox("To Party", options=parties)

        # Dropdown for State and District
        state_options = ['All'] + states
        selected_state = st.selectbox("State", options=state_options)
        state = None if selected_state == 'All' else selected_state

        district_options = ['All'] + districts
        selected_district = st.selectbox("District", options=district_options)
        district = None if selected_district == 'All' else selected_district

        # Simulate Button
        simulate_button = st.button("Simulate Redistribution")

        if simulate_button:
            if not from_parties:
                st.warning("Please select at least one 'From Party' to redistribute votes from.")
            elif not to_party:
                st.warning("Please select a 'To Party' to redistribute votes to.")
            else:
                # Perform redistribution
                updated_results = redistribute_votes(
                    all_results,
                    from_parties=from_parties,
                    to_party=to_party,
                    state=state if state else None,
                    district=district if district else None
                )

                # Prepare updated data
                updated_results, updated_winners = prepare_data(updated_results)

                # Debugging: Display columns to verify 'winner_name' exists
                st.write("Updated Results Columns:", updated_results.columns.tolist())

                # Check if 'winner_name' exists
                if 'winner_name' not in updated_results.columns:
                    st.error("The 'winner_name' column is missing after data preparation. Please check the data processing steps.")
                    return

                # Save results to session state
                st.session_state['updated_results'] = updated_results
                st.session_state['updated_winners'] = updated_winners
                st.session_state['simulation_run'] = True

                st.success("Vote redistribution simulation completed!")

        # =======================
        # Display Results
        # =======================
        if 'simulation_run' in st.session_state and st.session_state['simulation_run']:
            # Retrieve updated results from session state
            updated_results = st.session_state['updated_results']
            updated_winners = st.session_state['updated_winners']

            # Debugging: Display columns to verify 'winner_name' exists
            st.write("Updated Results After Simulation Columns:", updated_results.columns.tolist())

            # Prepare updated map data
            updated_map_df = pd.merge(
                geo_df,
                updated_winners[['state', 'district', 'winner_name', 'winner_party', 'winner_votes', 'margin_of_victory']],
                left_on=['state_name', 'district'],
                right_on=['state', 'district'],
                how='inner'
            )

            # Collect other candidates for updated results
            updated_other_candidates = (
                updated_results[updated_results['candidate'] != updated_results['winner_name']]
                .groupby(['state', 'district'])
                .apply(lambda group: group[['candidate', 'party', 'votes']].to_dict(orient='records'))
                .reset_index(name='other_candidates')
            )
            updated_map_df = pd.merge(updated_map_df, updated_other_candidates, on=['state', 'district'], how='left')

            # Convert to GeoDataFrame
            updated_map_df = gpd.GeoDataFrame(updated_map_df, geometry='geometry')

            # Compute vote share for the winning party
            def compute_vote_share_updated(row):
                if isinstance(row['other_candidates'], list):
                    other_votes = sum([c['votes'] for c in row['other_candidates']])
                else:
                    other_votes = 0
                total_votes = row['winner_votes'] + other_votes
                return (row['winner_votes'] / total_votes) * 100 if total_votes > 0 else 0

            updated_map_df['vote_share'] = updated_map_df.apply(compute_vote_share_updated, axis=1)

            # Define opacity based on vote_share
            def compute_opacity_updated(vote_share):
                if vote_share >= 85:
                    return 1.0
                elif vote_share >= 70:
                    return 0.8
                elif vote_share >= 55:
                    return 0.6
                elif vote_share >= 40:
                    return 0.4
                else:
                    return 0.2

            updated_map_df['fill_opacity'] = updated_map_df['vote_share'].apply(compute_opacity_updated)

            # Save the updated map data to session state
            st.session_state['updated_map_df'] = updated_map_df

            # Calculate and display the updated house scores
            updated_house_score = calculate_house_score(updated_winners)

            # Create tabs with the maps and scores
            updated_map_tabs = st.tabs(["Updated Results", "Original Results"])

            with updated_map_tabs[0]:
                st.subheader("Updated Election Results After Vote Redistribution")
                # Display updated house score
                updated_chart = plot_house_score(updated_house_score)
                st.altair_chart(updated_chart, use_container_width=True)

                if updated_map_df.empty:
                    st.error("The updated map data is empty after redistribution. Please check your inputs.")
                else:
                    updated_map_df['tooltip'] = updated_map_df.apply(create_tooltip, axis=1)
                    updated_map_html = create_map(geo_df, updated_map_df)
                    # Render the updated map HTML
                    html(updated_map_html, height=500)

            with updated_map_tabs[1]:
                st.subheader("Original Election Results")
                # Retrieve original map data from session state
                original_map_df = st.session_state['original_map_df']
                if original_map_df.empty:
                    st.error("The original map data is empty. Please check your inputs and data processing.")
                else:
                    original_map_df['tooltip'] = original_map_df.apply(create_tooltip, axis=1)
                    original_map_html = create_map(geo_df, original_map_df)
                    # Render the original map HTML
                    html(original_map_html, height=500)
        else:
            # Display original results initially in "Vote Redistribution" before any simulation
            st.subheader("Original Election Results")
            house_score = calculate_house_score(winners)
            chart = plot_house_score(house_score)
            st.altair_chart(chart, use_container_width=True)

            # Prepare map data
            geo_df['state_name'] = geo_df['state_name'].str.title()

            # Winning Party Map DataFrame
            map_df = pd.merge(
                geo_df,
                winners[['state', 'district', 'winner_name', 'winner_party', 'winner_votes', 'margin_of_victory']],
                left_on=['state_name', 'district'],
                right_on=['state', 'district'],
                how='inner'
            )

            # Collect other candidates
            other_candidates = (
                all_results[all_results['candidate'] != all_results['winner_name']]
                .groupby(['state', 'district'])
                .apply(lambda group: group[['candidate', 'party', 'votes']].to_dict(orient='records'))
                .reset_index(name='other_candidates')
            )

            # Merge other_candidates into map_df
            map_df = pd.merge(
                map_df,
                other_candidates,
                on=['state', 'district'],
                how='left'
            )

            # Convert to GeoDataFrame
            map_df = gpd.GeoDataFrame(map_df, geometry='geometry')

            # Compute vote share for the winning party
            def compute_vote_share(row):
                if isinstance(row['other_candidates'], list):
                    other_votes = sum([c['votes'] for c in row['other_candidates']])
                else:
                    other_votes = 0
                total_votes = row['winner_votes'] + other_votes
                return (row['winner_votes'] / total_votes) * 100 if total_votes > 0 else 0

            map_df['vote_share'] = map_df.apply(compute_vote_share, axis=1)

            # Define opacity based on vote_share
            # Opacity ranges from 0.5 (50%) to 1.0 (100%)
            def compute_opacity(vote_share):
                min_opacity = 0.5
                max_opacity = 1.0
                # Assuming vote_share ranges from 50% to 100%
                if vote_share < 50:
                    return min_opacity
                elif vote_share > 100:
                    return max_opacity
                else:
                    return min_opacity + (vote_share - 50) / 50 * (max_opacity - min_opacity)

            map_df['fill_opacity'] = map_df['vote_share'].apply(compute_opacity)

            # Collect other candidates
            other_candidates = (
                all_results[all_results['candidate'] != all_results['winner_name']]
                .groupby(['state', 'district'])
                .apply(lambda group: group[['candidate', 'party', 'votes']].to_dict(orient='records'))
                .reset_index(name='other_candidates')
            )

            # Merge other_candidates into map_df
            map_df = pd.merge(
                map_df,
                other_candidates,
                on=['state', 'district'],
                how='left'
            )

            # Save the original map data to session state
            st.session_state['original_map_df'] = map_df

            # Display the original map with tabs
            original_map_tabs = st.tabs(["Winning Party Map", "Weighted Opacity Map"])

            with original_map_tabs[0]:
                st.subheader("Winning Party Map")
                if map_df.empty:
                    st.error("The map data is empty. Please check your inputs and data processing.")
                else:
                    map_df['tooltip'] = map_df.apply(create_tooltip, axis=1)
                    map_html = create_map(geo_df, map_df)
                    # Render the map HTML
                    html(map_html, height=500)

            with original_map_tabs[1]:
                st.subheader("Weighted Opacity Map")
                if map_df.empty:
                    st.error("The map data is empty. Please check your inputs and data processing.")
                else:
                    # Create the map with opacity based on vote_share
                    weighted_map_html = create_map(geo_df, map_df, opacity_field='fill_opacity')
                    # Render the weighted opacity map HTML
                    html(weighted_map_html, height=500)

    elif analysis_type == "Analytical Questions":
        st.header("Analytical Questions")

        question = st.text_input("Enter your analytical question", value="Give me the five districts with the smallest margin of victory.")

        if st.button("Get Answer"):
            if "smallest margin" in question.lower():
                n = 5  # Default value
                match = re.search(r'(\d+)', question)
                if match:
                    n = int(match.group(1))
                smallest_margins = get_smallest_margins(winners, n=n)
                st.subheader(f"Top {n} Districts with Smallest Margin of Victory")
                st.table(smallest_margins)
            else:
                st.write("Sorry, I can only answer questions about the smallest margins of victory.")

    else:
        st.write("Please select an analysis type.")

if __name__ == "__main__":
    main()
