#region Using declarations
using System;
using System.Globalization;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Core;
using NinjaTrader.Data;
#endregion

// Export des bougies MGC pour l'analyste de Jabran (Salle des marchés, Documents\TradingAgents).
//
// LECTURE SEULE : c'est un indicateur, pas une stratégie. Il ne contient aucune fonction d'ordre :
// il ne peut ni envoyer, ni modifier, ni annuler un ordre, et ne touche à aucun compte.
//
// Ce qu'il fait : sur un graphique MGC en 1 minute, il écrit chaque bougie FERMÉE (1, 3, 5, 15 min, 1 h, jour)
// dans Documents\TradingAgents\donnees_ninja\MGC_<unité>.csv, et toutes les 2 s au plus, à chaque transaction,
// un petit fichier battement.json (contrat, dernier prix, heure) qui prouve que les données sont en direct.
// Heures en UTC, prix au point décimal (format indépendant de la langue de Windows).
// Une seule copie de l'indicateur à la fois (un seul graphique), sinon les fichiers se mélangent.
namespace NinjaTrader.NinjaScript.Indicators
{
	public class ExportBougiesMGC : Indicator
	{
		// l'ordre suit BarsInProgress : 0 = la série du graphique (1 minute), puis les séries ajoutées
		private static readonly string[] Noms = { "M1", "M3", "M5", "M15", "H1", "D1" };
		private static readonly int[] Minutes = { 1, 3, 5, 15, 60, 0 };
		private StreamWriter[] fichiers;
		private string dossier;
		private string erreur = "";
		private DateTime dernierBattement = DateTime.MinValue;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name						= "ExportBougiesMGC";
				Description					= "Écrit les bougies MGC fermées pour l'analyste (lecture seule, aucun ordre).";
				Calculate					= Calculate.OnBarClose;
				IsOverlay					= true;
				DisplayInDataBox			= false;
				PaintPriceMarkers			= false;
				IsSuspendedWhileInactive	= false;
			}
			else if (State == State.Configure)
			{
				AddDataSeries(BarsPeriodType.Minute, 3);
				AddDataSeries(BarsPeriodType.Minute, 5);
				AddDataSeries(BarsPeriodType.Minute, 15);
				AddDataSeries(BarsPeriodType.Minute, 60);
				AddDataSeries(BarsPeriodType.Day, 1);
			}
			else if (State == State.DataLoaded)
			{
				dossier = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "TradingAgents", "donnees_ninja");
				Directory.CreateDirectory(dossier);
				if (Instrument.MasterInstrument.Name != "MGC")
					erreur = "Le graphique doit être sur MGC (Micro Gold).";
				else if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 1)
					erreur = "Le graphique doit être en 1 minute.";
				fichiers = new StreamWriter[Noms.Length];
				for (int i = 0; i < Noms.Length; i++)
				{
					FileStream flux = new FileStream(Path.Combine(dossier, "MGC_" + Noms[i] + ".csv"), FileMode.Create, FileAccess.Write, FileShare.ReadWrite);
					fichiers[i] = new StreamWriter(flux) { AutoFlush = true };
					fichiers[i].WriteLine(Minutes[i] == 0 ? "date_seance,o,h,l,c,v" : "debut_utc,o,h,l,c,v");
				}
				EcrireBattement(double.NaN, "chargement");
			}
			else if (State == State.Terminated)
			{
				if (fichiers != null)
					foreach (StreamWriter f in fichiers)
						if (f != null)
							f.Dispose();
				fichiers = null;
			}
		}

		protected override void OnBarUpdate()
		{
			int i = BarsInProgress;
			if (fichiers == null || erreur.Length > 0 || i >= Noms.Length || CurrentBars[i] < 0)
				return;
			CultureInfo inv = CultureInfo.InvariantCulture;
			string quand;
			if (Minutes[i] == 0)
				quand = Times[i][0].Date.ToString("yyyy-MM-dd", inv);
			else
			{
				// NinjaTrader date une bougie à sa FERMETURE, dans le fuseau choisi dans ses options : on écrit son début en UTC
				DateTime fin = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(Times[i][0], DateTimeKind.Unspecified), Globals.GeneralOptions.TimeZoneInfo);
				quand = fin.AddMinutes(-Minutes[i]).ToString("yyyy-MM-ddTHH:mm:ssZ", inv);
			}
			fichiers[i].WriteLine(string.Join(",", quand, Prix(Opens[i][0]), Prix(Highs[i][0]), Prix(Lows[i][0]), Prix(Closes[i][0]),
				Volumes[i][0].ToString("0", inv)));
		}

		protected override void OnMarketData(MarketDataEventArgs e)
		{
			if (e.MarketDataType != MarketDataType.Last || fichiers == null)
				return;
			if ((DateTime.UtcNow - dernierBattement).TotalSeconds < 2)
				return;
			EcrireBattement(e.Price, erreur.Length > 0 ? "erreur" : "temps_reel");
		}

		private string Prix(double p)
		{
			return Instrument.MasterInstrument.RoundToTickSize(p).ToString("0.0###", CultureInfo.InvariantCulture);
		}

		private void EcrireBattement(double prix, string etat)
		{
			try
			{
				dernierBattement = DateTime.UtcNow;
				string texte = "{\"contrat\":\"" + Instrument.FullName + "\","
					+ "\"dernier_prix\":" + (double.IsNaN(prix) ? "null" : Prix(prix)) + ","
					+ "\"heure_utc\":\"" + dernierBattement.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture) + "\","
					+ "\"etat\":\"" + etat + "\","
					+ "\"erreur\":\"" + erreur.Replace("\"", "'") + "\"}";
				string cible = Path.Combine(dossier, "battement.json");
				string temporaire = cible + ".tmp";
				File.WriteAllText(temporaire, texte);
				if (File.Exists(cible))
					File.Replace(temporaire, cible, null);
				else
					File.Move(temporaire, cible);
			}
			catch (Exception ex)
			{
				Print("ExportBougiesMGC : " + ex.Message);
			}
		}
	}
}
