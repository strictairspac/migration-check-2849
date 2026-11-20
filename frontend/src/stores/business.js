import {batches,mappings,runs,drills} from '../api/business.js';
export const store={batches:[],mappings:[],runs:[],drillPackages:[],drillDetail:{},user:null};
export async function refresh(){[store.batches,store.mappings,store.runs,store.drillPackages]=await Promise.all([batches.list(),mappings.list(),runs.list(),drills.list()]);}
