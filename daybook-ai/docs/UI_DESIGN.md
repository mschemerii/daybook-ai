# Implemented UI Design

Daybook AI uses a wide but restrained Streamlit layout with a persistent horizontal navigation bar at the top. The sidebar and its collapse control are hidden. Native Streamlit theme variables support light and dark modes without fixed dark text.

Task information is shown in bordered cards. Each card has an explicit **Open task** control that navigates to an editable task-details view. Priority and status use text, icons, border treatment, and a color-blind-conscious palette, so color is never the only signal.

## Today

The page contains three compact metrics followed by Recommended focus, Due today, and Current blockers. Each task is an interactive card. Recommended tasks display a separate rule-explanation panel labeled **Selected by application rules**. The local model does not determine ordering.

## Tasks

The default view provides a collapsed Create task form and interactive task cards. Opening a card shows one task-details page with editable fields and Save changes, Mark complete, Delete task, and Back controls.

## Daily Journal

A date picker loads one entry. Five text areas match the required journal categories. A Save entry button persists locally. Ten recent entries appear below as expanders.

## Assistant

The page shows model connection status, explicit task and journal access checkboxes, memory retention disabled by default, a data-transfer notice, request box, and Send button. Results display local AI interpretation and consulted provenance. Memory and audit controls appear below.

## About

Plain explanatory content identifies the workforce need, local design, creator Michael Schemer, and prototype status. The Ethical AI button changes directly to the Ethical AI page.

## Ethical AI

Eight implemented principles are listed. An interactive selector categorizes example actions as Allowed, Requires confirmation, or Prohibited.
