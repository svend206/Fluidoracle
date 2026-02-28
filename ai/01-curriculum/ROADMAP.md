---
doc_id: curriculum_roadmap
doc_type: curriculum
status: active
version: 1.0
date: 2026-02-24
owner: Erik
authoring_agent: openclaw
supersedes: []
superseded_by: []
authoritative_sources: []
conflicts_with: []
tags: [curriculum, roadmap, overview]
---

# FilterOracle Curriculum Roadmap

## Philosophy

This curriculum builds the hydraulic filtration expert from first principles. Each phase deepens understanding of the domain before moving to the next. The goal is not to memorize product catalogs — it is to reason from physics, fluid mechanics, and contamination science to arrive at correct answers from first principles.

The fundamental unit of learning is: **Why does this work the way it does?** Not just what, but why.

## Phase 01: Fluid Mechanics Foundations

**Objective:** Understand the behavior of hydraulic fluids in motion — the foundation for everything else.

### Core Topics
- Viscosity (dynamic, kinematic, viscosity index) and measurement
- Newtonian vs. non-Newtonian fluids in hydraulic systems
- Reynolds number and flow regimes in hydraulic passages
- Pressure-flow relationships: Darcy-Weisbach, Hagen-Poiseuille
- Bernoulli's equation and hydraulic energy
- Pressure drop through orifices, valves, and fittings
- Hydraulic power transmission fundamentals
- Temperature effects on viscosity and system performance

### Key Milestones
- [ ] Can calculate pressure drop through a filter element given viscosity and flow
- [ ] Can explain why cold start is dangerous for filter elements
- [ ] Can calculate power losses due to filtration pressure drop
- [ ] Understands viscosity-temperature relationships and their practical implications

### Reference Material
- Parker Hannifin "Fluid Power Design Engineers Handbook"
- Manring "Hydraulic Control Systems" (Chapter 2 — fluid properties)
- ISO 3448 (Viscosity classification for industrial lubricants)

---

## Phase 02: Contamination Science

**Objective:** Understand what contamination is, where it comes from, how it is measured, and what it does to hydraulic components.

### Core Topics
- Particle morphology: hard particles, soft particles, fibers, water, air
- Contamination ingression sources: built-in (assembly), generated (wear), ingested (environmental)
- Component wear mechanisms: abrasive wear, fatigue wear, erosion
- Particle sizing methods: optical particle counters, laser diffraction, gravimetric analysis
- ISO 4406 cleanliness code system — calculation and interpretation
- NAS 1638 and SAE AS4059 cleanliness standards
- ISO 11171 calibration requirements for particle counters
- Clearances in hydraulic components and vulnerability to particle sizes
- Statistical contamination analysis and sampling protocols

### Key Milestones
- [ ] Can read and interpret ISO 4406 cleanliness codes correctly
- [ ] Can identify the primary contamination ingression paths in a hydraulic system
- [ ] Can convert between ISO 4406, NAS 1638, and SAE AS4059 codes
- [ ] Understands why different component types have different cleanliness requirements

### Reference Material
- ISO 4406:2021 (Hydraulic fluid power — Fluids — Method for coding the level of contamination)
- ISO 11171 (Hydraulic fluid power — Calibration of automatic particle counters)
- Noria Corporation "Machinery Lubrication" articles on contamination control
- Parker Hannifin "Contamination Control Technical Guide"

---

## Phase 03: Filtration Theory

**Objective:** Understand how filters work at the physics level — the mechanics of particle capture, media structure, and efficiency measurement.

### Core Topics
- Filter media microstructure: fiber diameter, porosity, tortuosity
- Particle capture mechanisms: mechanical sieving, inertial impaction, diffusion, electrostatic
- Beta ratio definition and measurement (ISO 16889 multi-pass test)
- Filter efficiency η = (1 - 1/β) and its implications
- Particle size distribution (PSD) and filtration across a spectrum of sizes
- Absolute vs. nominal filter ratings — the critical difference
- Dirt-holding capacity and service life prediction
- Single-pass vs. multi-pass filtration systems
- Bypass valve function and its effect on real-world efficiency

### Key Milestones
- [ ] Can calculate filter efficiency from beta ratio
- [ ] Can explain ISO 16889 multi-pass testing procedure
- [ ] Can determine required beta rating from target cleanliness code
- [ ] Understands the difference between absolute and nominal ratings

### Reference Material
- ISO 16889 (Hydraulic fluid power filters — Multi-pass method for evaluating filtration performance)
- Schweitzer "Handbook of Separation Techniques for Chemical Engineers"
- Parker Hannifin "Filter Technology" training module
- Donaldson "Fundamentals of Filtration" engineering guide

---

## Phase 04: Filter Engineering

**Objective:** Understand how filter elements and housings are designed — from media selection to mechanical integrity.

### Core Topics
- Filter element construction: pleated media, depth media, surface area calculation
- Pleat geometry optimization: depth, pitch, height, and their effect on ΔP and capacity
- Filter housing design: inlet/outlet geometry, bypass valve location, vent/drain ports
- Collapse pressure rating and the safety margin calculation
- Cold-start ΔP surge analysis and bypass risk assessment
- Filter element sealing: bypass-free seal design, anti-drain-back valves
- Absolute collapse ratings vs. differential collapse ratings
- High-pressure filter design (up to 420 bar): housing material selection, thread forms
- Return line filter design: low-pressure housing, tank mounting
- Suction filter design: vapor lock prevention, NPSH requirements
- Clogging indicator design: differential pressure switches, visual pop-up indicators, electronic ΔP sensors

### Key Milestones
- [ ] Can calculate filter surface area from element dimensions and pleat geometry
- [ ] Can verify a filter element selection against collapse pressure requirements
- [ ] Can specify a filter housing given system pressure, flow, and fluid specifications
- [ ] Understands the sealing considerations for bypass-free filtration

### Reference Material
- Filtration manufacturer technical datasheets (Parker, Donaldson, Hydac, Mahle, Argo-Hytos)
- ISO 10771 (Hydraulic fluid power — Fatigue pressure testing of metal pressure-containing envelopes)
- ISO 2941 (Hydraulic fluid power — Filter elements — Verification of collapse/burst resistance)

---

## Phase 05: System Integration

**Objective:** Understand how to design and specify the complete filtration system within a hydraulic circuit.

### Core Topics
- Filter placement strategies: pressure line, return line, off-line (kidney loop), suction
- Trade-offs of each placement location (protection level, pressure exposure, bypass risk)
- Kidney loop sizing: flow rate, residence time, and achieving target cleanliness
- System cleanliness modeling: beta ratio, ingression rate, reservoir size, flow rate
- New system flushing: procedure, flush media, target cleanliness, acceptance criteria
- Reservoir design for contamination control: settling zones, baffles, breathers
- Compressed air requirements for air-over-oil systems
- Multiple element configurations: series, parallel, duplex changeover
- Duplex filter systems: changeover under pressure, bypass-free switching
- Filtration circuit design for mobile equipment: space constraints, vibration, heat

### Key Milestones
- [ ] Can specify a complete filtration system for a standard industrial hydraulic circuit
- [ ] Can size a kidney loop for a target contamination level
- [ ] Can write a flushing specification for a new hydraulic system
- [ ] Understands the contamination balance equation and its practical application

### Reference Material
- Hydraulic Institute "Hydraulic System Design Guide"
- Parker Hannifin "Hydraulic Filtration System Design" application guide
- ISO 23309 (Hydraulic fluid power systems and components — Off-line filtration)

---

## Phase 06: Fluid Types & Compatibility

**Objective:** Understand the full range of hydraulic fluids and how fluid type affects filter selection.

### Core Topics
- Mineral oil hydraulics: refining process, additive packages, oxidation, degradation
- Polyalphaolefin (PAO) synthetics: advantages, compatibility considerations
- Phosphate ester fire-resistant fluids (HFD-R): chemical resistance requirements
- Water-glycol fire-resistant fluids (HFC): compatibility with zinc, cadmium, magnesium
- Water-in-oil emulsions (HFB) and oil-in-water emulsions (HFA)
- Biodegradable hydraulic fluids: HEES, HETG, HEPG
- Compatibility matrix: fluid vs. filter media (cellulose vs. glass fiber vs. synthetic)
- Compatibility matrix: fluid vs. seal materials (NBR, FKM, EPDM, PTFE)
- Fluid analysis and condition monitoring: viscosity, acidity (TAN), oxidation, water content
- Fluid change intervals and filtration implications

### Key Milestones
- [ ] Can specify the correct filter media for any standard hydraulic fluid type
- [ ] Can identify compatibility issues between fluid and filter materials
- [ ] Understands why cellulose media should not be used with water-based fluids
- [ ] Can specify the seal material for filter housings based on fluid type

### Reference Material
- ISO 6743-4 (Lubricants — Classification of lubricants for hydraulics)
- Lubrication Engineers "Hydraulic Fluid Compatibility Guide"
- ASTM D4627 (Test method for iron chip contamination from hydraulic fluid)

---

## Phase 07: Condition Monitoring

**Objective:** Understand how to monitor fluid and system condition to predict maintenance needs and catch problems early.

### Core Topics
- Oil sampling procedures: representative sampling from live systems, bottle preparation
- Automatic particle counters (APC): operating principles, calibration, measurement errors
- Gravimetric analysis (patch test): gravimetric weight, microscopic particle examination
- Ferrography: analytical ferrography for wear particle morphology analysis
- Spectroscopic analysis (ICP-OES): elemental analysis for wear metals, additives, contaminants
- Water content measurement: Karl Fischer titration, crackle test, capacitive sensors
- Total acid number (TAN) and total base number (TBN) analysis
- Viscosity measurement and kinematic vs. dynamic viscosity testing
- Differential pressure monitoring: trending ΔP to predict element change interval
- Integrated condition monitoring systems: sensors, data acquisition, alarming
- Root cause analysis from oil analysis results: identifying wear sources

### Key Milestones
- [ ] Can design an oil sampling program for an industrial hydraulic system
- [ ] Can interpret a comprehensive oil analysis report
- [ ] Can size a ΔP monitoring system for a filter bank
- [ ] Understands the statistical basis for oil analysis alarm limits

### Reference Material
- ASTM D6595 (Oil analysis by rotating disc electrode spectrometry)
- ISO 4021 (Hydraulic fluid power — Particulate contamination analysis — Extraction from system)
- Noria Corporation "Oil Analysis Handbook"
- Predict/DLI "Oil Analysis Learning Center"

---

## Phase 08: Standards & Compliance

**Objective:** Master the key standards that govern hydraulic filtration specification and testing.

### Core Topics
- ISO 16889 multi-pass test: procedure, equipment, data analysis, reporting
- ISO 4406 and ISO 11171: cleanliness coding with ISO MTD calibration
- ISO 2941, ISO 2942, ISO 2943: filter element integrity testing methods
- ISO 23181: filter elements — determination of resistance to flow fatigue
- NAS 1638 and SAE AS4059: aerospace cleanliness standards and conversion
- SAE J1165: reporting cleanliness levels of hydraulic fluids
- OEM cleanliness requirements: understanding manufacturer specifications
- CE marking and machinery directive requirements for filtration
- Factory acceptance testing (FAT): cleanliness verification procedures
- Condition monitoring standards: ISO 4407, ISO 4021

### Key Milestones
- [ ] Can specify filter element test requirements per ISO 16889
- [ ] Can verify OEM cleanliness compliance for a hydraulic system
- [ ] Can prepare a filtration specification document for a new machine design
- [ ] Understands the differences between ISO 4406:2021 and earlier revisions

### Reference Material
- ISO 16889:2022 (Multi-pass method for evaluating filtration performance of a filter element)
- ISO 4406:2021 (Method for coding level of contamination by solid particles)
- SAE J1165:2022 (Reporting cleanliness levels of hydraulic fluid)
- ISO 10771-1 (Fatigue pressure testing)

---

## Phase 09: Innovation & Advanced Topics

**Objective:** Understand the frontier of hydraulic filtration technology and emerging research directions.

### Core Topics
- Electrostatic oil filtration: principles, applications, effectiveness, limitations
- Nanofiber filter media: electrospun nanofibers, composite media structures, performance characteristics
- Magnetic filtration and separation: ferrous particle removal, permanent vs. electromagnetic
- Centrifugal oil cleaning: principles, applications in engine and industrial systems
- Predictive maintenance integration: IoT sensors, cloud data, ML-based prediction
- Smart differential pressure sensors: real-time monitoring, condition-based service intervals
- Advanced sealing technology: bypass-free designs, high-pressure zero-leak housings
- Water removal filtration: coalescer design, water absorption media, hydrophobic media
- Varnish removal filtration: cellulose inserts, electrostatic, depth filtration for dissolved oxidation products
- Ultrafine filtration (sub-1 µm): principles, applications in servo systems and precision hydraulics
- Filter element recycling and sustainability: used element handling, media material recovery

### Key Milestones
- [ ] Can evaluate the applicability of electrostatic filtration for a given application
- [ ] Can specify a varnish removal solution for a turbine lube system
- [ ] Understands the trade-offs between different polishing filtration approaches
- [ ] Can identify applications where predictive maintenance monitoring would be cost-justified

### Reference Material
- Recent publications from Filtration Society and BFPA (British Fluid Power Association)
- STLE Tribology Transactions — hydraulic fluid and filtration research
- IFPE (International Fluid Power Exposition) technical papers
- Hydac, Parker, Pall technical papers on advanced filtration technologies
