#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p python3Packages.beautifulsoup4 python3Packages.folium python3Packages.rich

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import folium
import requests
from branca.element import CssLink, Figure, JavascriptLink, MacroElement
from bs4 import BeautifulSoup
from jinja2 import Template
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress

console = Console()


class JsButton(MacroElement):
    """
    Button that executes a javascript function.
    Parameters
    ----------
    title : str
         title of the button, may contain html like
    function : str
         function to execute, should have format `function(btn, map) { ... }`

    See https://github.com/prinsherbert/folium-jsbutton.
    """

    _template = Template("""
        {% macro script(this, kwargs) %}
        L.easyButton(
            '<span>{{ this.title }}</span>',
            {{ this.function }}
        ).addTo({{ this.map_name }});
        {% endmacro %}
        """)

    def __init__(
        self,
        title="",
        function="""
        function(btn, map){
            alert('no function defined yet.');
        }
    """,
    ):
        super(JsButton, self).__init__()
        self.title = title
        self.function = function

    def add_to(self, m):
        self.map_name = m.get_name()
        super(JsButton, self).add_to(m)

    def render(self, **kwargs):
        super(JsButton, self).render()

        figure = self.get_root()
        assert isinstance(
            figure, Figure
        ), "You cannot render this Element if it is not in a Figure."

        figure.header.add_child(
            JavascriptLink(
                "https://cdn.jsdelivr.net/npm/leaflet-easybutton@2/src/easy-button.js"
            ),
            name="Control.EasyButton.js",
        )

        figure.header.add_child(
            CssLink(
                "https://cdn.jsdelivr.net/npm/leaflet-easybutton@2/src/easy-button.css"
            ),
            name="Control.EasyButton.css",
        )

        figure.header.add_child(
            CssLink("https://use.fontawesome.com/releases/v5.3.1/css/all.css"),
            name="Control.FontAwesome.css",
        )


@dataclass
class Event:
    link: str
    datetime: datetime
    lat: float = 0.0
    lon: float = 0.0

    def __hash__(self):
        return hash(self.link)

    @property
    def title(self):
        return (
            self.link.removeprefix("https://fftri.t2area.com/calendrier/")
            .removesuffix(".html")
            .replace("-", " ")
            .title()
        )


def extract_event_links_and_dates(html, base_url) -> set[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events: set[Event] = set()

    for li in soup.select("ul#adv-filter-gallery > li"):
        try:
            a_tag = li.select_one("h4.stories__headline a")
            time_tag = li.select_one("time[datetime]")

            if a_tag and time_tag:
                url = urljoin(base_url, a_tag["href"])
                date = time_tag["datetime"]
                events.add(Event(url, datetime.strptime(date, "%Y-%m-%d")))
        except Exception as e:
            console.log(f"[yellow]:warning: Issue parsing one event: {e}[/yellow]")

    console.log(
        f"[bold green]{len(events)} events found with URLs and dates[/bold green]"
    )
    return events


def extract_marker_positions(start_url):
    try:
        console.log(f"[bold blue]Loading start URL:[/bold blue] {start_url}")
        response = requests.get(start_url)
        response.raise_for_status()
    except requests.RequestException as e:
        console.log(f"[bold red]Failed to load {start_url}:[/bold red] {e}")
        return []

    events_info = extract_event_links_and_dates(response.text, start_url)

    marker_positions = []

    marker_pattern = re.compile(
        r"var\s+marker\s*=\s*L\.marker\(\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]"
    )

    with Progress() as progress:
        for evt in progress.track(events_info, description="Processing links..."):
            try:
                page = requests.get(evt.link)
                page.raise_for_status()
                match = marker_pattern.search(page.text)
                if match:
                    lat, lon = float(match.group(1)), float(match.group(2))
                    marker_positions.append(Event(evt.link, evt.datetime, lat, lon))
                    progress.console.log(
                        f":white_heavy_check_mark: [green]Found marker at:[/green] {lat}, {lon}"
                    )

                else:
                    progress.console.log(
                        f":warning: [yellow]No marker found in:[/yellow] {evt.link}"
                    )

            except requests.RequestException as e:
                progress.console.log(f":x: [red]Error fetching {evt.link}:[/red] {e}")
                continue

    return marker_positions


def generate_map(marker_positions: list[Event], output_file="build/index.html"):
    if not marker_positions:
        console.log("[red]No markers to plot.[/red]")
        return

    m = folium.Map(location=[48.856614, 2.3522219], zoom_start=6)

    JsButton(
        title='<i class="fas fa-crosshairs"></i>',
        function="""
        function(btn, map) {
            map.setView([48.856614, 2.3522219], 6);
            btn.state('zoom-to-forest');
        }
        """,
    ).add_to(m)

    for event in marker_positions:
        html = f'<a href="{event.link}" target="_blank"><b>{event.title}</b></a><br>Date: {event.datetime.strftime("%B %d, %Y")}'
        popup = folium.Popup(folium.IFrame(html, width=200, height=100), max_width=200)
        folium.Marker([event.lat, event.lon], popup=popup).add_to(m)

    m.save(output_file)
    console.log(f":world_map: [bold green]Map saved to:[/bold green] {output_file}")


# Example usage
if __name__ == "__main__":
    console.print(
        Panel(
            "📍 [bold cyan]Marker Extractor and Map Generator[/bold cyan]", expand=False
        )
    )
    url = "https://fftri.t2area.com/calendrier.html"  # Replace with your actual URL
    positions = []
    for i in range(0, 200, 10):
        positions += extract_marker_positions(url + f"?limitstart={i}")
    generate_map(positions)
