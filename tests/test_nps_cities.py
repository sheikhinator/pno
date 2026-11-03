"""4.2.3: NPS is by city and by format; a city's hypermarket score never reaches its supermarkets or Myli."""
from pno.po import canon
from pno.po.tabs import parse_nps


def _rows(lines):
    return [["Details", "Section", "Product Influence", "NPS"]] + [l.split("|") for l in lines]


def test_labels():
    assert canon.city("LHR NPS 2025") == "Lahore" and canon.city("ISB NPS 2025") == "Islamabad" and canon.city("FSD NPS 2025") == "Faisalabad"
    assert canon.store_in("Faisalabad NPS 2025") == "" and canon.store_in("Gujranwala NPS 2025") == ""      # a city, not its only store
    assert canon.store_in("LAH Fortress NPS 2025") == "LAH Fortress" and canon.store_in("Packages Mall Lahore NPS 2025") == "LAH Packages Mall"
    assert canon.nps_format("Lahore NPS 2025") == "Hypermarket" and canon.nps_format("Lahore Super NPS 2025") == "Supermarket"
    assert canon.nps_format("Lahore Myli NPS 2025") == "Health & Beauty" and canon.nps_format("x", "LAH Askari 10") == "Supermarket"


def test_hyper_survey_reaches_hypermarkets_only():
    from pno.po.insights import Insights

    class Store:
        def __init__(self, recs):
            self.recs = recs

    recs = parse_nps(_rows(["Lahore NPS 2025|Bakery|Bakery|40", "Lahore NPS 2025|DPH|Home care|60",
                            "Karachi NPS 2025|Bakery|Bakery|20", "LAH Fortress NPS 2025|Bakery|Bakery|90"]), "NPS").records
    ins = Insights.__new__(Insights)
    ins.rows = lambda kind: recs if kind == "po_nps" else []
    assert ins.nps("Lahore", store="LAH Packages Mall")["nps"] == 50                 # the city's hyper score
    assert ins.nps("Lahore", store="LAH Fortress")["nps"] == 90                      # its own line wins
    assert ins.nps("Lahore", store="LAH Askari 10") is None                          # a supermarket: not in the hyper survey
    assert ins.nps("Lahore", store="LAH Packages Mall · Myli") is None               # Myli: needs its own survey
    assert ins.nps("Karachi", store="KCH Lucky One")["nps"] == 20
