# Longer RoboCasa task candidates

Checked October 1, 2026 against the current official RoboCasa 1.0.1 catalog.
The current repository main commit is `456174f62b89b8fca99eaaf33949c29fec9cfc2a`,
which also matches our simulator source lock. This survey does not change the
benchmark task, release contract, or policy qualification status.

This list includes every catalog candidate with at least eight published
subtasks (38 tasks). Eight is a survey cutoff, not a universal definition of
long horizon. Sort order is descending subtask count, then descending rounded
median demonstration duration. All 38 are marked as requiring mobile manipulation.

Subtasks are RoboCasa's published counts, not counts invented from these
summaries. The catalog includes navigation among skills; do not interpret the
counts as that many distinct high-level object goals or guaranteed policy calls.
The duration column is the published demonstration median at 20 fps, not an
LLM runtime measurement or the environment's maximum rollout horizon. The data
file labels durations both mean_seconds and median_seconds; we explicitly use
median_seconds, consistent with its generation comment. The public page renders
mean_seconds under Horizon. These values agree for the candidates listed here.

Descriptions below paraphrase intended instructions. Current source paths were
verified for all candidates; instructions and success checks were directly
inspected for DivideBuffetTrays, PackFoodByTemp, PackIdenticalLunches,
PrepareCocktailStation, HotDogSetup, StoreDumplings, MakeBananaMilkshake, and
BlendMarinade. Other candidates still need a predicate audit before selection.
Instructions can specify stages that the final success predicate does not enforce.

| Task (source) | Published subtasks | Median demo duration | Intended work |
|---|---:|---:|---|
| [DivideBuffetTrays](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/arranging_buffet/divide_buffet_trays.py) | 16 | 166 s | Retrieve four foods from the fridge; separate vegetables and meats onto two serving trays. |
| [PackFoodByTemp](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/packing_lunches/pack_food_by_temp.py) | 15 | 123 s | Collect foods from fridge and stove areas; separate cold and warm foods into containers. |
| [PackIdenticalLunches](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/packing_lunches/pack_identical_lunches.py) | 15 | 87 s | Distribute four ingredients so each of two containers has one vegetable and one meat. |
| [PrepareCocktailStation](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/serving_beverages/prepare_cocktail_station.py) | 12 | 131 s | Retrieve a lemon, liquor, and glass from different locations; assemble them around a bowl. |
| [HotDogSetup](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/preparing_sandwiches/hot_dog_setup.py) | 12 | 104 s | Arrange bun and condiment at the dining table; retrieve sausage from the fridge and add it. |
| [PrepareDrinkStation](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/serving_beverages/prepare_drink_station.py) | 11 | 135 s | Bring cup, mug, and pitcher together at a serving tray. |
| [PlaceBeveragesTogether](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/arranging_buffet/place_beverages_together.py) | 11 | 91 s | Bring drinks together into a compact cluster at the dining counter. |
| [StoreDumplings](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/storing_leftovers/store_dumplings.py) | 11 | 91 s | Distribute four dumplings between two containers; move both filled containers into the fridge. |
| [BuildAppetizerPlate](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/filling_serving_dishes/build_appetizer_plate.py) | 11 | 90 s | Collect cheese, meat, and a vegetable from the fridge onto one serving plate. |
| [DisplayMeatVariety](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/filling_serving_dishes/display_meat_variety.py) | 11 | 90 s | Retrieve three kinds of meat from the fridge onto a serving tray. |
| [SetUpSpiceStation](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/seasoning_food/setup_spice_station.py) | 11 | 84 s | Bring spice, bottle, and shaker from the cabinet to the stove area. |
| [ClearFreezer](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/managing_freezer_space/clear_freezer.py) | 11 | 82 s | Transfer foods from the freezer into a counter bowl. |
| [CreateChildFriendlyFridge](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/loading_fridge/create_child_friendly_fridge.py) | 11 | 82 s | Rearrange alcohol onto an upper shelf and snacks onto lower shelves. |
| [ClearSinkArea](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/cleaning_sink/clear_sink_area.py) | 11 | 77 s | Relocate mugs and a bowl away from the sink. |
| [MakeBananaMilkshake](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/mixing_and_blending/make_banana_milkshake.py) | 11 | 76 s | Stage honey and milk near the blender; insert banana into the jug. Blending is not required. |
| [SeparateRawIngredients](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/sorting_ingredients/separate_raw_ingredients.py) | 11 | 50 s | Separate meat or seafood onto a cutting board and vegetables into a bowl. |
| [RecycleSodaCans](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/organizing_recycling/recycle_soda_cans.py) | 9 | 146 s | Collect four scattered cans into a cluster near the stove. |
| [BeverageSorting](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/restocking_supplies/beverage_sorting.py) | 9 | 102 s | Separate alcoholic and nonalcoholic drinks between two cabinets. |
| [BlendMarinade](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/preparing_marinade/blend_marinade.py) | 9 | 73 s | Retrieve two vegetables, load the blender, close its lid, and activate it. |
| [PrepareVeggieDip](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/mixing_ingredients/prepare_veggie_dip.py) | 9 | 69 s | Retrieve vegetable and cream cheese, load the blender, and activate it. |
| [LoadCondimentsInFridge](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/loading_fridge/load_condiments_in_fridge.py) | 9 | 57 s | Put condiments on the upper fridge shelf; relocate existing items if necessary. |
| [SetBowlsForSoup](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/setting_the_table/set_bowls_for_soup.py) | 8 | 135 s | Transfer cabinet bowls onto plates at the dining table. |
| [ReturnWashingSupplies](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/washing_dishes/return_washing_supplies.py) | 8 | 119 s | Return cleaning supplies from the sink area to a cabinet. |
| [DateNight](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/setting_the_table/date_night.py) | 8 | 110 s | Bring decoration and alcohol from a cabinet to the dining counter. |
| [CandleCleanup](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/clearing_table/candle_cleanup.py) | 8 | 100 s | Put dining-table decorations into an open cabinet and close it. |
| [AlcoholServingPrep](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/serving_food/alcohol_serving_prep.py) | 8 | 98 s | Open a cabinet and bring alcohol and a cup to the decorated dining counter. |
| [PlateStoreDinner](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/plating_food/plate_store_dinner.py) | 8 | 95 s | Divide steaks between a plate and bowl; store the bowl in the fridge. |
| [SetupButterPlate](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/setting_the_table/setup_butter_plate.py) | 8 | 95 s | Bring refrigerated butter to a dining-table plate and put a butter knife nearby. |
| [ArrangeBuffetDessert](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/arranging_buffet/arrange_buffet_dessert.py) | 8 | 91 s | Transfer refrigerated sweets onto a serving tray. |
| [SetupSodaBowl](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/serving_beverages/setup_soda_bowl.py) | 8 | 91 s | Open the fridge; transfer two sodas into the ice bowl at the dining counter. |
| [FreezeBottledWaters](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/managing_freezer_space/freeze_bottled_waters.py) | 8 | 90 s | Move water bottles into the freezer and close its door. |
| [SetupFruitBowl](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/setting_the_table/setup_fruit_bowl.py) | 8 | 90 s | Bring refrigerated fruits to a bowl on the dining table. |
| [SeasoningSpiceSetup](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/setting_the_table/seasoning_spice_setup.py) | 8 | 88 s | Bring cabinet condiments to the dining counter. |
| [PrepareSausageCheese](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/preparing_sandwiches/prepare_sausage_cheese.py) | 8 | 85 s | Bring refrigerated sausage and cheese to a cutting board. |
| [ClearReceptaclesForCleaning](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/clearing_table/clear_receptacles_for_cleaning.py) | 8 | 78 s | Move tableware into the sink and start the water. |
| [PrewashFoodSorting](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/washing_fruits_and_vegetables/prewash_food_sorting.py) | 8 | 75 s | Put cabinet foods in one bowl and sink foods in another. |
| [CoolBakedCake](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/baking/cool_baked_cake.py) | 8 | 69 s | Move cake from the oven onto a plate and close the oven. |
| [PlaceVeggiesInDrawer](https://github.com/robocasa/robocasa/blob/456174f62b89b8fca99eaaf33949c29fec9cfc2a/robocasa/environments/kitchen/composite/loading_fridge/place_veggies_in_drawer.py) | 8 | 42 s | Put vegetables into a fridge drawer and close it. |

## Implications for OrcaBench

CerealAndBowl has four published subtasks and a 79-second demonstration median.
The upper end of the existing catalog reaches 16 subtasks and 166 seconds.
More subtasks do not establish supervisory difficulty: many candidates mainly
repeat retrieval and placement with navigation.

StoreDumplings is a promising dependency test: preserve the contents while
moving filled containers. BlendMarinade provides a different skill mix through
retrieval, insertion, lid handling, and activation. Its final checker requires
both vegetables inside and the blender on; lid closure is in the instruction
but is not a separate conjunct of the final checker. DivideBuffetTrays and
PackIdenticalLunches are promising larger inventory/assignment tasks. These are
research priorities, not qualified benchmark tasks or measured policy results.
MakeBananaMilkshake stages ingredients; its name should not be interpreted as
requiring the blender to run.

Long duration and composition length are different: ArrangeUtensilsByType has
four subtasks / 126 s, ClearSink four / 125 s, and ArrangeTea three / 116 s.
They are excluded by this survey's count threshold even though demonstrations
are lengthy.

## Sources and reusable data

- [Official composite catalog](https://robocasa.ai/docs/build/html/tasks/composite_tasks.html)
- [Published subtask counts](https://robocasa.ai/docs/build/html/static/composite_task_attributes.js)
- [Published demonstration durations](https://robocasa.ai/docs/build/html/static/composite_episode_lengths.js)
- [Published task descriptions](https://robocasa.ai/docs/build/html/static/task_attributes.json?v=2)
- [CSV with trial counts and individual source links](long_horizon_tasks.csv)

No simulator, model inference, or GPU rental was used for this survey.
