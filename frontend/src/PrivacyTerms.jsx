import React from 'react'
import { PageLink } from './AppNavigation.jsx'
import ScreenTabs from './ScreenTabs.jsx'
import './HowItWorks.css'

// Plain-language privacy notice and terms. Every statement mirrors what the code does (see update.md, 27 Oct 2026);
// change this page whenever data handling changes.
export default function PrivacyTerms({ navigate }) {
  return <div className="how privacy-terms">
    <ScreenTabs mode="always" label="Privacy and terms" tabs={[
      { id: 'privacy', label: 'Privacy', content: <section className="panel" aria-labelledby="privacy-title">
        <h2 id="privacy-title">What FloodPulse does with your data</h2>
        <ul className="how-steps">
          <li><strong>No accounts, ads or tracking.</strong> Citizens do not sign up. There are no analytics or advertising cookies, and data is never sold.</li>
          <li><strong>Your location</strong> is used to show weather, warnings, risk and shelters for your place. FloodPulse passes the point to Open-Meteo (weather, river flow, ground height) and, for routes, to openrouteservice; if you choose Google Maps directions, Google receives the start and end. Street addresses come from OpenStreetMap Nominatim with the point rounded to about 11 m. Town names come from BigDataCloud, asked directly by your device. Map images come from OpenStreetMap's servers, which see the area you view. FloodPulse stores your location only if you submit a report.</li>
          <li><strong>Flood reports</strong> (description, location, time and an optional photo — kept as a cleaned copy without camera metadata, plus the original only if you tick the box allowing its metadata) are seen only by project administrators. They are not published and not used to train any model. Photos are deleted after 7 days and the private details after 30 days; a record of the review decision is kept. You can withdraw a report while its page stays open.</li>
          <li><strong>Telegram district alerts.</strong> Your Telegram chat ID is stored only to send the administrator-approved alerts for the districts you chose. /stop deletes it (blocking the bot does too). The log of subscribe and stop commands keeps a scrambled identifier, not the chat ID.</li>
          <li><strong>Administrators</strong> use a sign-in cookie that expires after 30 idle minutes or 8 hours; sign-in attempts are limited and their actions are recorded in an audit log.</li>
          <li><strong>Logs.</strong> Server logs record which page or service was used, not the coordinates in web addresses. If the app crashes, the page and a short error message are logged under an error ID.</li>
        </ul>
        <p className="muted">FloodPulse is a student project. To ask about or remove your data, contact the project team.</p>
      </section> },
      { id: 'terms', label: 'Terms of use', content: <section className="panel" aria-labelledby="terms-title">
        <h2 id="terms-title">Terms of use</h2>
        <ul className="how-steps">
          <li><strong>Not an official warning service.</strong> FloodPulse is a student prototype. Follow IMD, KSNDMC, NDMA SACHET and your district administration. In an emergency call <a href="tel:112">112</a> or the Karnataka emergency centre <a href="tel:0801070">080-1070</a>.</li>
          <li><strong>Predictions are experimental.</strong> The risk index is rule-based and is not a flood probability; the AI models can be wrong (see <PageLink to="/model-performance" navigate={navigate}>Model performance</PageLink>).</li>
          <li><strong>Shelters and routes.</strong> Shelter details are checked by administrators but can change; capacity is not a reservation. Routes are not verified flood-safe — confirm access before you travel.</li>
          <li><strong>Alerts</strong> may be delayed or not delivered, and are sent only after an administrator approves them.</li>
          <li><strong>Reports</strong> must be honest and your own; only upload photos you have the right to share. Administrators may reject any report.</li>
          <li><strong>Data sources</strong> keep their licences: Open-Meteo (CC BY 4.0), OpenStreetMap (ODbL), official warnings as issued by IMD and NDMA.</li>
          <li><strong>No warranty.</strong> The service is provided as is and may be unavailable at times.</li>
        </ul>
        <p className="muted">Last updated 27 October 2026.</p>
      </section> },
    ]} />
  </div>
}
